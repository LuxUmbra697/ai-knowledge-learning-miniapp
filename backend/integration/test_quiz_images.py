import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest
from app.llm.quiz_chain import validate_quiz
from app.models.quiz import QuizGenerateRequest
from app.repositories import job_repository as jobs
from app.repositories import quiz_image_repository as assets
from app.repositories import quiz_repository
from app.repositories.rag_index_repository import transaction
from app.services import history_service, quiz_task_service
from app.services import quiz_image_service as images
from app.worker import TaskContext
from fastapi import HTTPException
from integration.test_quiz_tasks import OUTPUT


async def fixture(user, monkeypatch):
    monkeypatch.setattr(images, 'require_config', lambda: None)
    req = QuizGenerateRequest(user_input='Synthetic illustration fixture', question_count=3, generate_images=True)
    task = await quiz_task_service.create(req, user, uuid.uuid4().hex)
    context = TaskContext(await jobs.claim())
    result = await quiz_repository.publish_generated_quiz(context, validate_quiz(OUTPUT, 3, 'mixed'))
    return task, result, TaskContext(await jobs.claim())


@pytest.mark.asyncio
async def test_text_commits_before_images_and_cancellation_does_not_remove_quiz(users, monkeypatch):
    task, result, context = await fixture(users[0], monkeypatch)
    assert (await jobs.get_owned(task['task_id'], users[0]))['status'] == 'completed'
    assert context.kind == 'image' and context.payload['quiz_id'] == result['quiz_id']
    detail = await history_service.get_quiz_detail(result['quiz_id'], users[0])
    assert len([q for q in detail.questions if q.get('image_asset_id')]) == 2
    assert all('answer' not in q for q in detail.questions)
    rows = await assets.for_task(context)
    await assets.reserve(context, rows[0]['asset_id'])
    await jobs.cancel(context.task_id, users[0])
    with pytest.raises(jobs.TaskLeaseLost):
        await assets.finish(context, [{'asset_id': row['asset_id'], 'state': 'ready'} for row in rows])
    assert (await images.get_image(rows[0]['asset_id'], users[0]))['status'] == 'failed'
    assert await history_service.get_quiz_detail(result['quiz_id'], users[0]) is not None
    with pytest.raises(HTTPException) as error:
        await images.get_image(rows[0]['asset_id'], users[1])
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_image_daily_quota_is_reserved_atomically_and_replay_does_not_spend_again(users, monkeypatch):
    _, _, context = await fixture(users[0], monkeypatch)
    rows = await assets.for_task(context)
    monkeypatch.setattr(assets, 'get_settings', lambda: type('Settings', (), {'image_gen_daily_limit': 1})())
    results = await asyncio.gather(*(assets.reserve(context, row['asset_id']) for row in rows), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, HTTPException) and result.status_code == 429 for result in results) == 1
    winner = next(result for result in results if isinstance(result, dict))
    await assets.reserve(context, winner['asset_id'])
    async with transaction() as cur:
        await cur.execute('SELECT COUNT(*) AS n FROM quiz_image_assets WHERE user_id=%s AND reserved_day IS NOT NULL', (users[0],))
        assert (await cur.fetchone())['n'] == 1


@pytest.mark.asyncio
async def test_failed_image_provider_is_not_retried_per_question_and_text_remains(users, monkeypatch):
    _, result, context = await fixture(users[0], monkeypatch)
    monkeypatch.setattr(images.storage, 'verify_storage', AsyncMock())
    generate = AsyncMock(side_effect=HTTPException(503, 'Synthetic authorization failure'))
    monkeypatch.setattr(images, 'generate', generate)
    complete = await images.run(context)
    assert complete['image_count'] == 0
    generate.assert_awaited_once()
    assert (await jobs.get_owned(context.task_id, users[0]))['trace']['model_calls'] == 1
    assert await history_service.get_quiz_detail(result['quiz_id'], users[0]) is not None


@pytest.mark.asyncio
async def test_image_publication_rollback_preserves_unpublished_assets(users, monkeypatch):
    _, _, context = await fixture(users[0], monkeypatch)
    rows = await assets.for_task(context)
    monkeypatch.setattr(jobs, 'publish_result', AsyncMock(side_effect=RuntimeError('Synthetic publication failure')))
    with pytest.raises(RuntimeError):
        await assets.finish(context, [{'asset_id': row['asset_id'], 'state': 'ready'} for row in rows])
    async with transaction() as cur:
        await cur.execute('SELECT state FROM quiz_image_assets WHERE task_id=%s', (context.task_id,))
        assert {row['state'] for row in await cur.fetchall()} == {'pending'}


@pytest.mark.asyncio
async def test_image_publication_fences_source_versions_inside_transaction(users, monkeypatch):
    _, _, context = await fixture(users[0], monkeypatch)
    rows = await assets.for_task(context)
    context.payload['scope'] = [['doc_removed_fixture', 1, 'obsolete-version']]
    async with transaction() as cur:
        await cur.execute('UPDATE learning_jobs SET payload_json=%s WHERE task_id=%s', (jobs.encoded(context.payload), context.task_id))
    with pytest.raises(HTTPException) as error:
        await assets.finish(context, [{'asset_id': row['asset_id'], 'state': 'ready'} for row in rows])
    assert error.value.status_code == 409
    async with transaction() as cur:
        await cur.execute('SELECT state FROM quiz_image_assets WHERE task_id=%s', (context.task_id,))
        assert {row['state'] for row in await cur.fetchall()} == {'pending'}


@pytest.mark.asyncio
async def test_ready_image_is_revealed_only_after_authoritative_submission(users, monkeypatch):
    from app.services.grading_service import AnswerSubmission, submit_question
    _, result, context = await fixture(users[0], monkeypatch)
    rows = await assets.for_task(context)
    await assets.finish(context, [{'asset_id': row['asset_id'], 'state': 'ready'} for row in rows])
    hidden = await images.get_image(rows[0]['asset_id'], users[0])
    assert hidden['status'] == 'locked' and hidden['url'] is None
    detail = await history_service.get_quiz_detail(result['quiz_id'], users[0])
    assert all('knowledge_point' not in question and 'image_url' not in question for question in detail.questions)
    await submit_question(result['quiz_id'], users[0], AnswerSubmission(question_id=rows[0]['question_id'], selected_answers=['A']))
    monkeypatch.setattr(images.storage, 'signed_url', lambda _: 'https://private.example/short-lived')
    shown = await images.get_image(rows[0]['asset_id'], users[0])
    assert shown['status'] == 'ready' and shown['expires_in'] == 120
    assert (await images.get_image(rows[1]['asset_id'], users[0]))['status'] == 'locked'


@pytest.mark.asyncio
async def test_exhausted_child_task_admission_still_commits_text_and_cleanup_retries_are_bounded(users, monkeypatch):
    original = jobs.insert
    async def quota(cur, user, kind, payload, key, status='queued'):
        if kind == 'image':
            raise HTTPException(429, 'Synthetic daily task cap')
        return await original(cur, user, kind, payload, key, status)
    monkeypatch.setattr(jobs, 'insert', quota)
    monkeypatch.setattr(images, 'require_config', lambda: None)
    task = await quiz_task_service.create(QuizGenerateRequest(user_input='No child slot', generate_images=True, question_count=3), users[0], uuid.uuid4().hex)
    context = TaskContext(await jobs.claim())
    result = await quiz_repository.publish_generated_quiz(context, validate_quiz(OUTPUT, 3, 'mixed'))
    assert (await jobs.get_owned(task['task_id'], users[0]))['status'] == 'completed'
    detail = await history_service.get_quiz_detail(result['quiz_id'], users[0])
    assert '未安排配图' in detail.image_notice
    assert not any(question.get('image_asset_id') for question in detail.questions)
    monkeypatch.setattr(jobs, 'insert', original)
    _, _, image_task = await fixture(users[0], monkeypatch)
    rows = await assets.for_task(image_task)
    await jobs.cancel(image_task.task_id, users[0])
    for _ in range(5):
        await assets.cleanup_failed(rows[0]['asset_id'])
    async with transaction() as cur:
        await cur.execute('UPDATE quiz_image_assets SET updated_at=UTC_TIMESTAMP()-INTERVAL 11 MINUTE WHERE task_id=%s', (image_task.task_id,))
    candidates = await assets.cleanup_candidates()
    assert rows[0]['asset_id'] not in {row['asset_id'] for row in candidates}
    assert rows[1]['asset_id'] in {row['asset_id'] for row in candidates}
