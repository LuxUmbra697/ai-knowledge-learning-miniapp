import asyncio
import json
import uuid
from unittest.mock import AsyncMock

import pytest
from app.models.evidence import evidence_from_row
from app.models.tutor import TutorCreate, TutorTurn
from app.repositories import job_repository as jobs
from app.repositories import rag_index_repository as index
from app.repositories import tutor_repository as repository
from app.services import tutor_graph as graph
from app.services import tutor_service as service
from app.services import vector_store_service as vectors
from app.worker import TaskContext
from fastapi import HTTPException
from integration.test_quiz_tasks import OUTPUT
from integration.test_quiz_tasks import fixture as quiz_fixture


async def fixture(user):
    request, unused = await quiz_fixture(user)
    await jobs.cancel(unused['task_id'], user)
    req = TutorCreate(goal='Why save checkpoints?', doc_ids=[request.doc_id])
    key = uuid.uuid4().hex
    session = await service.create(user, req, key)
    assert (await service.create(user, req, key))['session_id'] == session['session_id']
    evidence = evidence_from_row((await index.scoped_chunks(user, [request.doc_id], vectors.index_version()))[0], 'E1').model_dump()
    return req, session, evidence


def reply():
    return {'status': 'hint', 'hint': '先区分任务本身和任务的恢复点。', 'question': '重启后应该从哪里继续？',
            'citations': [{'evidence_id': 'E1', 'quote': 'tasks and checkpoints are persisted'}], 'diagnosis': None,
            'practice': {'count': 2, 'focus': 'checkpoint recovery'}}


async def checkpoint(context, evidence):
    await context.checkpoint('tutor_evidence', {'status': 'ok', 'evidence': [evidence]})
    await context.checkpoint('tutor_coach', {'output': [{'content': json.dumps(reply()), 'finish_reason': 'stop'}]})


@pytest.mark.asyncio
async def test_tutor_owned_idempotent_turns_resume_without_model_calls(users, monkeypatch):
    request, session, evidence = await fixture(users[0])
    monkeypatch.setattr(graph.tutor_chain, 'get_chat_model', lambda **_: pytest.fail('Saved response must not call a provider'))
    with pytest.raises(HTTPException) as denied:
        await service.create(users[1], request)
    assert denied.value.status_code == 404
    for action in (lambda: service.detail(session['session_id'], users[1]), lambda: repository.delete(session['session_id'], users[1])):
        with pytest.raises(HTTPException) as denied:
            await action()
        assert denied.value.status_code == 404
    req, key = TutorTurn(version=0, message='I think a process variable is sufficient.'), uuid.uuid4().hex
    tasks = await asyncio.gather(*(service.turn(session['session_id'], users[0], req, key) for _ in range(3)))
    assert len({task['task_id'] for task in tasks}) == 1
    context = TaskContext(await jobs.claim())
    await checkpoint(context, evidence)
    async with index.transaction() as cur:
        await cur.execute('UPDATE learning_jobs SET lease_until=UTC_TIMESTAMP()-INTERVAL 1 SECOND WHERE task_id=%s', (context.task_id,))
    restored = TaskContext(await jobs.claim())
    result = await graph.run(restored)
    assert result == {'session_id': session['session_id'], 'turn': 1}
    detail = await service.detail(session['session_id'], users[0])
    assert detail['version'] == 1 and len(detail['turns']) == 1 and detail['pending_task_id'] is None
    answer = detail['turns'][0]['response']
    assert answer['practice']['requires_confirmation'] and not answer['practice']['created']
    task = await jobs.get_owned(context.task_id, users[0])
    assert task['trace']['model_calls'] == 0 and set(task['result']) == {'session_id', 'turn'}
    assert (await service.turn(session['session_id'], users[0], req, key))['task_id'] == context.task_id
    with pytest.raises(HTTPException) as stale:
        await service.turn(session['session_id'], users[0], TutorTurn(version=0, message='Changed answer'))
    assert stale.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['cancel', 'delete_source', 'commit'])
async def test_tutor_publication_is_atomic_and_fenced(users, monkeypatch, failure):
    request, session, evidence = await fixture(users[0])
    await service.turn(session['session_id'], users[0], TutorTurn(version=0, message='Hint please'))
    context = TaskContext(await jobs.claim())
    await checkpoint(context, evidence)
    if failure == 'cancel':
        await jobs.cancel(context.task_id, users[0])
    elif failure == 'delete_source':
        await index.tombstone(request.doc_ids[0], users[0])
    else:
        monkeypatch.setattr(jobs, 'publish_result', AsyncMock(side_effect=RuntimeError('Synthetic failed commit')))
    with pytest.raises((jobs.TaskLeaseLost, HTTPException, RuntimeError)):
        await graph.run(context)
    assert (await repository.get(session['session_id'], users[0]))['version'] == 0
    assert await repository.turns(session['session_id'], users[0]) == []


@pytest.mark.asyncio
async def test_tutor_serializes_competing_turns_and_allows_cancelled_turn_retry(users):
    _, session, _ = await fixture(users[0])
    async def submit(message):
        return await service.turn(session['session_id'], users[0], TutorTurn(version=0, message=message))
    results = await asyncio.gather(submit('First answer'), submit('Different device'), return_exceptions=True)
    assert sum(isinstance(item, dict) for item in results) == 1
    assert sum(isinstance(item, HTTPException) and item.status_code == 409 for item in results) == 1
    first = next(item for item in results if isinstance(item, dict))
    with pytest.raises(HTTPException):
        await repository.delete(session['session_id'], users[0])
    await jobs.cancel(first['task_id'], users[0])
    retry = await submit('Explicit retry')
    assert retry['task_id'] != first['task_id']
    await jobs.cancel(retry['task_id'], users[0])
    await repository.delete(session['session_id'], users[0])
    with pytest.raises(HTTPException):
        await service.detail(session['session_id'], users[0])


@pytest.mark.asyncio
async def test_diagnosis_reads_owned_actual_wrong_answer_not_client_correctness(users):
    from app.repositories.quiz_repository import save_quiz_session
    from app.services.grading_service import AnswerSubmission, submit_question
    from app.services.learning_state_service import cards
    quiz_id = 'quiz_' + uuid.uuid4().hex
    await save_quiz_session(quiz_id, users[0], OUTPUT['title'], OUTPUT['summary'], 'synthetic', OUTPUT['questions'])
    await submit_question(quiz_id, users[0], AnswerSubmission(question_id='q1', selected_answers=['B']))
    card = (await cards(users[0], 'wrong'))[0]
    request = TutorCreate(goal='Help me diagnose this answer', mode='diagnosis', card_id=card['card_id'])
    session = await service.create(users[0], request)
    assert session['doc_ids'] == []
    material = await service.practice_material(users[0], card['card_id'])
    assert material['record']['selected_answers'] == ['B'] and material['question']['answer'] == ['A']
    assert material['confirmed_diagnosis'] is None
    assert (await service.detail(session['session_id'], users[0]))['confirmed_diagnosis'] is None
    from app.services.learning_state_service import CardSettings, update_card
    await update_card(card['card_id'], users[0], CardSettings(diagnosis='concept_confusion'))
    assert (await service.detail(session['session_id'], users[0]))['confirmed_diagnosis'] == 'concept_confusion'
    with pytest.raises(HTTPException) as error:
        await service.create(users[1], request)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_tutor_six_turn_cap_two_turn_memory_and_no_evidence_branch(users, monkeypatch):
    _, session, evidence = await fixture(users[0])
    monkeypatch.setattr(graph.tutor_chain, 'get_chat_model', lambda **_: pytest.fail('Deterministic checkpoints must not call a provider'))
    for version in range(6):
        await service.turn(session['session_id'], users[0], TutorTurn(version=version, message=f'Synthetic answer {version}'))
        context = TaskContext(await jobs.claim())
        if version == 0:
            await context.checkpoint('tutor_evidence', {'status': 'empty', 'evidence': []})
        else:
            await checkpoint(context, evidence)
        await graph.run(context)
    result = await service.detail(session['session_id'], users[0])
    assert result['version'] == 6 and len(result['turns']) == 6
    assert result['turns'][0]['response']['status'] == 'no_evidence'
    assert result['turns'][-1]['response']['memory_turns'] == 2
    assert all(turn['response']['tool_summary']['fresh_tool_calls'] <= 4 for turn in result['turns'])
    with pytest.raises(HTTPException) as error:
        await service.turn(session['session_id'], users[0], TutorTurn(version=5, message='Seventh turn must not be admitted'))
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_confirmed_practice_uses_saved_proposal_and_one_owned_idempotent_job(users):
    from app.models.tutor import TutorPracticeConfirm
    _, session, evidence = await fixture(users[0])
    await service.turn(session['session_id'], users[0], TutorTurn(version=0, message='Synthetic first reply'))
    context = TaskContext(await jobs.claim())
    await checkpoint(context, evidence)
    await graph.run(context)
    command = TutorPracticeConfirm(version=1, confirmed=True)
    first = await service.confirm_practice(session['session_id'], users[0], 1, command)
    second = await service.confirm_practice(session['session_id'], users[0], 1, command)
    assert first['task_id'] == second['task_id']
    async with index.transaction() as cur:
        await cur.execute('SELECT payload_json FROM learning_jobs WHERE task_id=%s', (first['task_id'],))
        payload = repository.decoded((await cur.fetchone())['payload_json'])
    assert payload['question_count'] == 2 and payload['query'] == 'checkpoint recovery'
    assert payload['doc_ids'] == session['doc_ids']
    assert not payload.get('generate_images') and not payload.get('use_web_search')
    with pytest.raises(HTTPException) as denied:
        await service.confirm_practice(session['session_id'], users[1], 1, command)
    assert denied.value.status_code == 404
