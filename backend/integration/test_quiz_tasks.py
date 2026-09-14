"""Real isolated MySQL: source fencing, cancellation, rollback and cached-response recovery."""
import asyncio
import hashlib
import json
import uuid

from fastapi import HTTPException
from langchain_core.documents import Document
import pytest

from app.llm.quiz_chain import validate_quiz
from app.models.quiz import QuizGenerateRequest
from app.repositories import job_repository as jobs, quiz_repository, rag_index_repository as index
from app.services import quiz_task_service as service, vector_store_service as vectors
from app.services.grading_service import public_quiz
from app.worker import TaskContext


OUTPUT = {'title': 'Synthetic private practice', 'summary': 'Deterministic recovery fixture', 'questions': [
    dict(id='q1', type='single', stem='What is used for recovery?', options=[{'key': 'A', 'text': 'Checkpoint'}, {'key': 'B', 'text': 'Guess'}],
         answer=['A'], explanation='Use a saved checkpoint.', knowledge_point='recovery', difficulty='easy'),
    dict(id='q2', type='multiple', stem='Which are persisted?', options=[{'key': 'A', 'text': 'Task'}, {'key': 'B', 'text': 'Checkpoint'}, {'key': 'C', 'text': 'Thread'}],
         answer=['A', 'B'], explanation='The task and checkpoint are persisted.', knowledge_point='persistence', difficulty='easy'),
    dict(id='q3', type='judge', stem='Cancellation prevents publication.', options=[{'key': 'A', 'text': '正确'}, {'key': 'B', 'text': '错误'}],
         answer=['A'], explanation='The transaction checks its lease.', knowledge_point='cancellation', difficulty='easy'),
]}


async def fixture(user):
    doc_id = 'doc_' + uuid.uuid4().hex
    text = 'Synthetic source: tasks and checkpoints are persisted. Cancellation prevents publication.'
    version = vectors.index_version()
    doc = await index.reserve(doc_id, user, 'Synthetic practice.md', 'md', len(text), hashlib.sha256(text.encode()).hexdigest(), version, 10)
    await index.publish(doc_id, user, 1, version, [Document(page_content=text, metadata={'chunk_id': 'c1'})])
    await jobs.cancel(doc['task_id'], user)
    req = QuizGenerateRequest(user_input='Private checkpoint practice', doc_id=doc_id, question_count=3)
    task = await service.create(req, user, uuid.uuid4().hex)
    return req, task


async def quiz_count(task_id):
    async with index.transaction() as cur:
        await cur.execute('SELECT COUNT(*) AS n FROM quiz_sessions WHERE quiz_id=%s', ('quiz_' + task_id[4:],))
        return (await cur.fetchone())['n']


@pytest.mark.asyncio
async def test_quiz_reclaims_known_response_without_calling_models_and_hides_answers(users):
    req, task = await fixture(users[0])
    duplicate = await service.create(req, users[0], uuid.uuid4().hex)
    assert duplicate['task_id'] == task['task_id']
    with pytest.raises(HTTPException) as error:
        await service.create(req, users[1], uuid.uuid4().hex)
    assert error.value.status_code == 404
    claimed = TaskContext(await jobs.claim())
    await claimed.checkpoint('quiz_sources', 'Synthetic authorized source')
    await jobs.reserve_call(claimed.task_id, claimed.lease_token, 'quiz')
    await jobs.complete_call(claimed.task_id, claimed.lease_token, 'quiz',
                             {'output': [{'content': json.dumps(OUTPUT), 'finish_reason': 'stop'}]}, 10)
    async with index.transaction() as cur:
        await cur.execute('UPDATE learning_jobs SET lease_until=UTC_TIMESTAMP()-INTERVAL 1 SECOND WHERE task_id=%s', (claimed.task_id,))
    restored = TaskContext(await jobs.claim())
    reference = await service.run(restored)
    assert await quiz_count(task['task_id']) == 1
    saved = await jobs.get_owned(task['task_id'], users[0])
    assert saved['status'] == 'completed' and saved['result'] == reference and saved['trace']['model_calls'] == 1
    assert set(reference) == {'quiz_id', 'title'}
    visible = public_quiz((await service.status(task['task_id'], users[0])).result.model_dump())
    assert all('answer' not in q and 'explanation' not in q for q in visible['questions'])
    with pytest.raises(HTTPException) as error:
        await service.status(task['task_id'], users[1])
    assert error.value.status_code == 404
    with pytest.raises(jobs.TaskLeaseLost):
        await quiz_repository.publish_generated_quiz(restored, validate_quiz(OUTPUT, 3, 'mixed'))
    assert await quiz_count(task['task_id']) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('invalidate', ['cancel', 'delete', 'reindex'])
async def test_changed_source_or_cancelled_job_cannot_publish(users, invalidate):
    req, task = await fixture(users[0])
    context = TaskContext(await jobs.claim())
    if invalidate == 'cancel':
        await jobs.cancel(task['task_id'], users[0])
    elif invalidate == 'delete':
        await index.tombstone(req.doc_id, users[0])
    else:
        await index.begin_reindex(req.doc_id, users[0], vectors.index_version())
    with pytest.raises((jobs.TaskLeaseLost, HTTPException)):
        await quiz_repository.publish_generated_quiz(context, validate_quiz(OUTPUT, 3, 'mixed'))
    assert await quiz_count(task['task_id']) == 0


@pytest.mark.asyncio
async def test_failed_final_task_write_rolls_back_generated_quiz(users, monkeypatch):
    _req, task = await fixture(users[0])
    context = TaskContext(await jobs.claim())
    async def fail(*_args):
        raise RuntimeError('Synthetic final task write failure')
    monkeypatch.setattr(jobs, 'publish_result', fail)
    with pytest.raises(RuntimeError):
        await quiz_repository.publish_generated_quiz(context, validate_quiz(OUTPUT, 3, 'mixed'))
    assert await quiz_count(task['task_id']) == 0
    assert (await jobs.get_owned(task['task_id'], users[0]))['status'] == 'running'


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['quiz', 'answer', 'retrieve', 'report'])
async def test_coalesced_second_device_key_remains_bound_after_completion(users, kind):
    payload = {'query': 'Synthetic admission-only check'}
    first = await jobs.enqueue(users[0], kind, payload, 'first-device-key')
    second = await jobs.enqueue(users[0], kind, payload, 'second-device-key')
    assert first['task_id'] == second['task_id']
    context = TaskContext(await jobs.claim())
    await jobs.finish(context.task_id, context.lease_token, {'quiz_id': 'synthetic-reference'})
    replay = await jobs.enqueue(users[0], kind, payload, 'second-device-key')
    assert replay['task_id'] == first['task_id']
    with pytest.raises(HTTPException) as error:
        await jobs.enqueue(users[0], kind, {'query': 'Changed request'}, 'second-device-key')
    assert error.value.status_code == 409
    explicit_new = await jobs.enqueue(users[0], kind, payload, 'new-practice-key')
    assert (explicit_new['task_id'] == first['task_id']) == (kind == 'report')


@pytest.mark.asyncio
async def test_coalesced_keys_are_bounded_and_existing_keys_still_replay(users):
    task = await jobs.enqueue(users[0], 'quiz', {}, 'original-key')
    for number in range(64):
        assert (await jobs.enqueue(users[0], 'quiz', {}, f'alias-key-{number}'))['task_id'] == task['task_id']
    with pytest.raises(HTTPException) as error:
        await jobs.enqueue(users[0], 'quiz', {}, 'extra-alias-key')
    assert error.value.status_code == 429
    assert (await jobs.enqueue(users[0], 'quiz', {}, 'alias-key-0'))['task_id'] == task['task_id']
    other = await jobs.enqueue(users[1], 'quiz', {}, 'alias-key-0')
    assert other['task_id'] != task['task_id']


@pytest.mark.asyncio
async def test_coalesced_key_does_not_wait_for_running_job_while_holding_user_lock(users):
    task = await jobs.enqueue(users[0], 'report', {'quiz_id': 'synthetic'}, 'original-report-key')
    async with index.transaction() as cur:
        await cur.execute('SELECT task_id FROM learning_jobs WHERE task_id=%s FOR UPDATE', (task['task_id'],))
        # A report publisher can hold the job while acquiring the user's XP row next.
        replay = await asyncio.wait_for(jobs.enqueue(users[0], 'report', {'quiz_id': 'synthetic'}, 'another-report-key'), timeout=2)
        assert replay['task_id'] == task['task_id']
