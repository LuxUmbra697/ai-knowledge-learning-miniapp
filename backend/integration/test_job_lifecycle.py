"""Real MySQL task ownership, idempotency, fencing, cancellation and uncertain-call recovery."""
import asyncio
import uuid
import subprocess
import sys
from pathlib import Path

from fastapi import HTTPException
import pytest

from app.repositories import job_repository as jobs
from app.repositories.rag_index_repository import transaction


@pytest.mark.asyncio
async def test_idempotency_is_owned_atomic_and_payload_checked(users):
    key = uuid.uuid4().hex
    first, second = await asyncio.gather(jobs.enqueue(users[0], 'answer', {'query': 'A'}, key),
                                         jobs.enqueue(users[0], 'answer', {'query': 'A'}, key))
    assert first['task_id'] == second['task_id']
    assert sorted([first['replayed'], second['replayed']]) == [False, True]
    with pytest.raises(HTTPException) as error:
        await jobs.enqueue(users[0], 'answer', {'query': 'B'}, key)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        await jobs.get_owned(first['task_id'], users[1])
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_only_one_worker_claims_and_expired_worker_cannot_publish(users):
    task = await jobs.enqueue(users[0], 'answer', {}, uuid.uuid4().hex)
    claims = await asyncio.gather(jobs.claim(), jobs.claim())
    assert sum(row is not None for row in claims) == 1
    claim = next(row for row in claims if row)
    async with transaction() as cur:
        await cur.execute('UPDATE learning_jobs SET lease_until=UTC_TIMESTAMP()-INTERVAL 1 SECOND WHERE task_id=%s', (task['task_id'],))
    recovered = await jobs.claim()
    assert recovered['lease_token'] != claim['lease_token']
    assert not await jobs.finish(task['task_id'], claim['lease_token'], {'answer': 'stale'})
    assert await jobs.finish(task['task_id'], recovered['lease_token'], {'answer': 'current'})
    assert (await jobs.get_owned(task['task_id'], users[0]))['result'] == {'answer': 'current'}


@pytest.mark.asyncio
async def test_cancellation_wins_against_late_completion(users):
    task = await jobs.enqueue(users[0], 'answer', {}, uuid.uuid4().hex)
    claim = await jobs.claim()
    with pytest.raises(HTTPException) as error:
        await jobs.cancel(task['task_id'], users[1])
    assert error.value.status_code == 404
    assert (await jobs.cancel(task['task_id'], users[0]))['status'] == 'cancelled'
    assert not await jobs.finish(task['task_id'], claim['lease_token'], {'answer': 'late'})
    assert not await jobs.heartbeat(task['task_id'], claim['lease_token'])


@pytest.mark.asyncio
async def test_uncertain_external_call_does_not_repeat_after_crash(users):
    task = await jobs.enqueue(users[0], 'answer', {}, uuid.uuid4().hex)
    claim = await jobs.claim()
    await jobs.reserve_call(task['task_id'], claim['lease_token'], 'answer')
    async with transaction() as cur:
        await cur.execute('UPDATE learning_jobs SET lease_until=UTC_TIMESTAMP()-INTERVAL 1 SECOND WHERE task_id=%s', (task['task_id'],))
    assert await jobs.claim() is None
    status = await jobs.get_owned(task['task_id'], users[0])
    assert status['status'] == 'failed' and status['error_code'] == 'external_outcome_unknown'


@pytest.mark.asyncio
async def test_call_attempts_survive_checkpoint_and_stop_at_three(users):
    task = await jobs.enqueue(users[0], 'answer', {}, uuid.uuid4().hex)
    claim = await jobs.claim()
    for expected in range(1, 4):
        assert await jobs.reserve_call(task['task_id'], claim['lease_token'], 'answer') == expected
        await jobs.complete_call(task['task_id'], claim['lease_token'], 'answer', {'diagnostic': 'invalid_json'}, 10)
    with pytest.raises(jobs.TaskBudgetExceeded):
        await jobs.reserve_call(task['task_id'], claim['lease_token'], 'answer')
    state = await jobs.get_owned(task['task_id'], users[0])
    assert state['trace']['model_calls'] == 3 and state['trace']['tokens'] == 30


@pytest.mark.asyncio
async def test_success_requires_external_output_checkpoint(users):
    task = await jobs.enqueue(users[0], 'answer', {}, uuid.uuid4().hex)
    claim = await jobs.claim()
    await jobs.reserve_call(task['task_id'], claim['lease_token'], 'answer')
    assert not await jobs.finish(task['task_id'], claim['lease_token'], {'unverified': True})
    assert (await jobs.get_owned(task['task_id'], users[0]))['status'] == 'running'
    await jobs.complete_call(task['task_id'], claim['lease_token'], 'answer', {'verified': True}, 1)
    assert await jobs.finish(task['task_id'], claim['lease_token'], {'verified': True})


@pytest.mark.asyncio
async def test_global_provider_budget_is_atomic_across_users(users, monkeypatch):
    tasks = [await jobs.enqueue(user, 'answer', {}, uuid.uuid4().hex) for user in users]
    claims = [await jobs.claim(), await jobs.claim()]
    async with transaction() as cur:
        await cur.execute('SELECT calls FROM provider_call_budget WHERE budget_day=UTC_DATE()')
        row = await cur.fetchone()
    settings = jobs.get_settings().model_copy(update={'worker_daily_provider_calls': (row['calls'] if row else 0) + 1})
    monkeypatch.setattr(jobs, 'get_settings', lambda: settings)
    attempts = await asyncio.gather(*(jobs.reserve_call(claim['task_id'], claim['lease_token'], 'answer', 10) for claim in claims), return_exceptions=True)
    assert sum(isinstance(result, jobs.TaskBudgetExceeded) for result in attempts) == 1
    states = [await jobs.get_owned(task['task_id'], user) for task, user in zip(tasks, users)]
    assert sum(state['trace']['model_calls'] for state in states) == 1


@pytest.mark.asyncio
async def test_isolated_suite_starts_with_fresh_budget_without_disabling_limits(users):
    async with transaction() as cur:
        await cur.execute('SELECT calls,input_bytes FROM provider_call_budget WHERE budget_day=UTC_DATE()')
        assert await cur.fetchone() == {'calls': 0, 'input_bytes': 0}
    assert jobs.get_settings().worker_daily_provider_calls == 100


@pytest.mark.asyncio
async def test_input_budget_refuses_before_counting_call(users):
    task = await jobs.enqueue(users[0], 'answer', {}, uuid.uuid4().hex)
    claim = await jobs.claim()
    with pytest.raises(jobs.TaskBudgetExceeded):
        await jobs.reserve_call(task['task_id'], claim['lease_token'], 'answer', 60001)
    assert (await jobs.get_owned(task['task_id'], users[0]))['trace']['model_calls'] == 0


@pytest.mark.asyncio
async def test_duplicate_call_completion_is_rejected_without_changing_usage(users):
    task = await jobs.enqueue(users[0], 'answer', {}, uuid.uuid4().hex)
    claim = await jobs.claim()
    await jobs.reserve_call(task['task_id'], claim['lease_token'], 'answer')
    await jobs.complete_call(task['task_id'], claim['lease_token'], 'answer', {}, 10)
    with pytest.raises(jobs.TaskLeaseLost):
        await jobs.complete_call(task['task_id'], claim['lease_token'], 'answer', {}, 10)
    assert (await jobs.get_owned(task['task_id'], users[0]))['trace']['tokens'] == 10


@pytest.mark.asyncio
async def test_failed_index_retains_cleanup_grace_for_interrupted_native_call(users):
    from test_index_lifecycle import reserve
    from app.repositories import rag_index_repository as index
    doc = await reserve(users[0])
    await jobs.activate(doc['task_id'], users[0])
    claim = await jobs.claim()
    await jobs.reserve_call(doc['task_id'], claim['lease_token'], 'embedding_0')
    await jobs.finish(doc['task_id'], claim['lease_token'], None, 'timeout', 'timeout')
    await index.tombstone(doc['doc_id'], users[0])
    await index.cleanup_done(doc['doc_id'], users[0])
    async with transaction() as cur:
        await cur.execute('SELECT cleanup_pending FROM kb_index_meta WHERE doc_id=%s', (doc['doc_id'],))
        assert (await cur.fetchone())['cleanup_pending'] == 1


@pytest.mark.asyncio
async def test_cancel_of_completed_answer_cannot_return_deleted_evidence(users):
    from test_index_lifecycle import reserve
    from app.repositories import rag_index_repository as index
    from langchain_core.documents import Document
    doc = await reserve(users[0])
    await index.publish(doc['doc_id'], users[0], 1, 'v1', [Document(page_content='evidence', metadata={'chunk_id': 'c1'})])
    task = await jobs.enqueue(users[0], 'answer', {}, uuid.uuid4().hex)
    claim = await jobs.claim()
    result = {'status': 'answered', 'claims': [], 'evidence': [{'doc_id': doc['doc_id'], 'chunk_id': 'c1', 'revision': 1}]}
    await jobs.finish(task['task_id'], claim['lease_token'], result)
    await index.tombstone(doc['doc_id'], users[0])
    cancelled = await jobs.cancel(task['task_id'], users[0])
    assert cancelled['status'] == 'completed'
    assert cancelled['result']['status'] == 'stale_evidence' and not cancelled['result']['evidence']


@pytest.mark.asyncio
async def test_delete_keeps_cleanup_pending_while_cancelled_thread_can_finish(users):
    from test_index_lifecycle import reserve
    from app.repositories import rag_index_repository as index
    doc = await reserve(users[0])
    await jobs.activate(doc['task_id'], users[0])
    claim = await jobs.claim()
    await index.tombstone(doc['doc_id'], users[0])
    await index.cleanup_done(doc['doc_id'], users[0])
    async with transaction() as cur:
        await cur.execute('SELECT cleanup_pending FROM kb_index_meta WHERE doc_id=%s', (doc['doc_id'],))
        assert (await cur.fetchone())['cleanup_pending'] == 1
        await cur.execute('UPDATE learning_jobs SET lease_until=UTC_TIMESTAMP()-INTERVAL 120 SECOND WHERE task_id=%s', (claim['task_id'],))
    assert any(row['doc_id'] == doc['doc_id'] for row in await index.maintenance_rows())
    await index.cleanup_done(doc['doc_id'], users[0])
    async with transaction() as cur:
        await cur.execute('SELECT cleanup_pending FROM kb_index_meta WHERE doc_id=%s', (doc['doc_id'],))
        assert (await cur.fetchone())['cleanup_pending'] == 0


@pytest.mark.asyncio
async def test_actual_worker_process_restarts_from_persisted_checkpoint(users):
    task = await jobs.enqueue(users[0], 'answer', {'synthetic': True}, uuid.uuid4().hex)
    script = Path(__file__).with_name('worker_probe.py')
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    process = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    try:
        for _ in range(60):
            state = await jobs.get_owned(task['task_id'], users[0])
            if state['stage'] == 'restart_probe':
                break
            await asyncio.sleep(.1)
        assert state['stage'] == 'restart_probe'
    finally:
        process.terminate()
        await asyncio.to_thread(process.wait, 10)
    async with transaction() as cur:
        await cur.execute('UPDATE learning_jobs SET lease_until=UTC_TIMESTAMP()-INTERVAL 1 SECOND WHERE task_id=%s', (task['task_id'],))
    completed = await asyncio.to_thread(subprocess.run, [sys.executable, str(script)], capture_output=True, timeout=15, creationflags=flags)
    assert completed.returncode == 0
    state = await jobs.get_owned(task['task_id'], users[0])
    assert state['status'] == 'completed'
    assert state['result'] == {'recovered': True, 'external_calls': 0}
