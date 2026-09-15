from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.models.companion import CompanionTurn, MemoryUpdate, MemoryItem, ResetConversation
from app.repositories import companion_repository as repository, job_repository as jobs
from app.repositories.rag_index_repository import transaction
from app.services import companion_service
from app.worker import TaskContext


def reply():
    return {'dialogue': '先把这一页看完，再慢慢聊。', 'emotion': 'calm', 'action': 'read',
            'used_memory_ids': [], 'memory_suggestion': None}


@pytest.mark.asyncio
async def test_memory_is_user_and_character_scoped_versioned_and_forgettable(users):
    first = await repository.detail(users[0], 'pink')
    assert first['version'] == 0
    await repository.set_memories(users[0], 'pink', MemoryUpdate(version=0, items=[MemoryItem(id='study', kind='study', text='喜欢番茄钟')]))
    assert (await repository.detail(users[0], 'pink'))['memories'][0]['text'] == '喜欢番茄钟'
    assert (await repository.detail(users[0], 'orange'))['memories'] == []
    assert (await repository.detail(users[1], 'pink'))['memories'] == []
    with pytest.raises(HTTPException) as error:
        await repository.set_memories(users[0], 'pink', MemoryUpdate(version=0, items=[]))
    assert error.value.status_code == 409
    await repository.set_memories(users[0], 'pink', MemoryUpdate(version=1, items=[]))
    assert (await repository.detail(users[0], 'pink'))['memories'] == []


@pytest.mark.asyncio
async def test_admission_deduplication_cancel_reset_fences_worker_and_scrubs_content(users):
    command = CompanionTurn(version=0, message='private test message')
    task = await repository.admit(users[0], 'pink', command, 'companion_test_001')
    repeated = await repository.admit(users[0], 'pink', command, 'companion_test_001')
    assert repeated['task_id'] == task['task_id']
    with pytest.raises(HTTPException):
        await repository.admit(users[0], 'pink', CompanionTurn(version=0, message='different'), 'companion_test_002')
    context = TaskContext(await jobs.claim())
    await repository.reset(users[0], 'pink', ResetConversation(version=0, mode='all', confirmed=True))
    with pytest.raises((HTTPException, jobs.TaskLeaseLost)):
        await repository.publish(context, reply())
    async with transaction() as cur:
        await cur.execute('SELECT payload_json,state_json,result_json,status FROM learning_jobs WHERE task_id=%s', (task['task_id'],))
        row = await cur.fetchone()
        assert 'private test message' not in str(row)
        assert row['status'] == 'cancelled'
    after = await repository.detail(users[0], 'pink')
    assert after['turns'] == [] and after['turn_count'] == 0 and after['version'] == 1


@pytest.mark.asyncio
async def test_actual_worker_publication_and_memory_context_are_owned(users, monkeypatch):
    await repository.set_memories(users[0], 'pink', MemoryUpdate(version=0, items=[MemoryItem(id='study', kind='study', text='喜欢番茄钟')]))
    task = await repository.admit(users[0], 'pink', CompanionTurn(version=1, message='今天学一点'), 'companion_publish_001')
    context = TaskContext(await jobs.claim())
    generate = AsyncMock(return_value=reply())
    monkeypatch.setattr(companion_service.chain, 'generate', generate)
    result = await companion_service.run(context)
    assert result['character_id'] == 'pink'
    material = generate.call_args.args[0]
    assert material['memories'][0]['text'] == '喜欢番茄钟'
    assert 'user_id' not in material and len(material['story']) == 1
    detail = await repository.detail(users[0], 'pink')
    assert detail['version'] == 2 and detail['turn_count'] == 1 and len(detail['turns']) == 1
    assert (await jobs.get_owned(task['task_id'], users[0]))['status'] == 'completed'
    assert (await repository.detail(users[1], 'pink'))['turns'] == []
    await repository.reset(users[0], 'pink', ResetConversation(version=2, mode='history', confirmed=True))
    after = await repository.detail(users[0], 'pink')
    assert after['turns'] == [] and len(after['memories']) == 1 and after['turn_count'] == 1


@pytest.mark.asyncio
async def test_cancelled_turn_does_not_publish_and_other_character_survives_reset(users):
    await repository.set_memories(users[0], 'orange', MemoryUpdate(version=0, items=[MemoryItem(id='support', kind='support', text='简洁具体')]))
    await repository.admit(users[0], 'pink', CompanionTurn(version=0, message='本轮将被取消'), 'companion_cancel_001')
    context = TaskContext(await jobs.claim())
    await jobs.cancel(context.task_id, users[0])
    with pytest.raises(jobs.TaskLeaseLost):
        await repository.publish(context, reply())
    assert (await repository.detail(users[0], 'pink'))['turn_count'] == 0
    await repository.reset(users[0], 'pink', ResetConversation(version=0, mode='memory', confirmed=True))
    assert (await repository.detail(users[0], 'orange'))['memories'][0]['text'] == '简洁具体'


@pytest.mark.asyncio
async def test_unknown_paid_outcome_is_not_retried_and_reset_does_not_reset_daily_quota(users):
    task = await repository.admit(users[0], 'pink', CompanionTurn(version=0, message='restart boundary'), 'companion_unknown_001')
    async with transaction() as cur:
        await cur.execute('UPDATE learning_jobs SET state_json=%s WHERE task_id=%s', ('{"call_pending":true}', task['task_id']))
    assert await jobs.claim() is None
    assert (await jobs.get_owned(task['task_id'], users[0]))['error_code'] == 'external_outcome_unknown'
    await repository.reset(users[0], 'pink', ResetConversation(version=0, mode='all', confirmed=True))
    async with transaction() as cur:
        await cur.execute("SELECT COUNT(*) AS n FROM learning_jobs WHERE user_id=%s AND kind='companion'", (users[0],))
        assert (await cur.fetchone())['n'] == 1
