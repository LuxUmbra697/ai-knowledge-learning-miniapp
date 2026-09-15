"""Isolated MySQL only: retry admission, shared budgets and restart fencing."""
import asyncio

from fastapi import HTTPException
import pytest

from app.models.quiz import QuizGenerateRequest
from app.repositories import job_repository as jobs
from app.repositories.rag_index_repository import transaction
from app.services import quiz_task_service as service


@pytest.mark.asyncio
async def test_quiz_retry_is_owned_idempotent_and_reuses_original_blueprint(users):
    original = await service.create(QuizGenerateRequest(user_input='Synthetic retry practice', question_count=2), users[0], 'retry-original')
    with pytest.raises(HTTPException) as error:
        await service.retry(original['task_id'], users[1])
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        await service.retry(original['task_id'], users[0])
    assert error.value.status_code == 409
    await jobs.cancel(original['task_id'], users[0])
    first, second = await asyncio.gather(service.retry(original['task_id'], users[0]), service.retry(original['task_id'], users[0]))
    assert first['task_id'] == second['task_id'] != original['task_id']
    claimed = await jobs.claim()
    assert claimed['payload_json']['question_count'] == 2
    assert claimed['payload_json']['query'] == 'Synthetic retry practice'
    await jobs.finish(claimed['task_id'], claimed['lease_token'], {'quiz_id': 'synthetic'})
    assert (await service.retry(original['task_id'], users[0]))['task_id'] == first['task_id']


@pytest.mark.asyncio
async def test_quiz_shared_ten_call_budget_survives_batches_and_recovery(users):
    task = await service.create(QuizGenerateRequest(user_input='Synthetic batch retry', question_count=10), users[0], 'retry-budget')
    claim = await jobs.claim()
    for number in range(10):
        stage = 'quiz_batch_1' if number < 6 else 'quiz_batch_2'
        await jobs.reserve_call(task['task_id'], claim['lease_token'], stage, 13000)
        await jobs.complete_call(task['task_id'], claim['lease_token'], stage, {}, 4000)
    status = await jobs.get_owned(task['task_id'], users[0])
    assert status['generation'] == {'attempts': 10, 'max_attempts': 10}
    async with transaction() as cur:
        await cur.execute('UPDATE learning_jobs SET lease_until=UTC_TIMESTAMP()-INTERVAL 1 SECOND,started_at=UTC_TIMESTAMP()-INTERVAL 200 SECOND WHERE task_id=%s', (task['task_id'],))
    restored = await jobs.claim()
    assert restored and restored['task_id'] == task['task_id']
    with pytest.raises(jobs.TaskBudgetExceeded):
        await jobs.reserve_call(task['task_id'], restored['lease_token'], 'quiz_batch_3', 1)
    assert (await jobs.get_owned(task['task_id'], users[0]))['trace']['model_calls'] == 10


@pytest.mark.asyncio
async def test_retry_api_rejects_identity_and_input_tampering(users):
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.auth import create_token
    task = await service.create(QuizGenerateRequest(user_input='Owned API retry', question_count=1), users[0], 'api-retry-key')
    await jobs.cancel(task['task_id'], users[0])
    url = '/api/v1/learning/tasks/' + task['task_id'] + '/retry'
    headers = {'Authorization': 'Bearer ' + create_token(users[0], 'synthetic')}
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.post(url, json={})).status_code == 401
        other = {'Authorization': 'Bearer ' + create_token(users[1], 'synthetic')}
        assert (await client.post(url, json={}, headers=other)).status_code == 404
        for body in [{'user_id': users[1]}, {'doc_id': 'other'}, {'question_count': 100}, {'is_correct': True}]:
            assert (await client.post(url, json=body, headers=headers)).status_code == 422
        result = await client.post(url, json={}, headers=headers)
        assert result.status_code == 200
        assert result.json()['data']['task_id'] != task['task_id']
        assert all(key not in result.json()['data'] for key in ('payload_json', 'state_json', 'questions', 'lease_token'))


@pytest.mark.asyncio
async def test_retry_deleted_private_document_does_not_enqueue(users):
    task = await jobs.enqueue(users[0], 'quiz', dict(query='Removed source', question_count=1, difficulty='mixed',
        doc_ids=['doc_removed'], scope=[['doc_removed', 1, 'old']], mode='rerank'), 'removed-source-key')
    await jobs.cancel(task['task_id'], users[0])
    with pytest.raises(HTTPException) as error:
        await service.retry(task['task_id'], users[0])
    assert error.value.status_code == 404
    assert len(await jobs.list_owned(users[0])) == 1
