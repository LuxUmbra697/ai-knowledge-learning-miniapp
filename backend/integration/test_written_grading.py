"""Isolated MySQL: no model is invoked; persisted provider outputs exercise actual recovery."""
import asyncio
import json
import uuid

import pytest
from app.repositories import job_repository as jobs
from app.repositories import quiz_repository as quizzes
from app.repositories.rag_index_repository import transaction
from app.services import learning_state_service as learning
from app.services import written_grade_service as service
from app.services.grading_service import AnswerSubmission, get_attempts, public_quiz
from app.worker import TaskContext
from fastapi import HTTPException

QUESTION = {'id': 'q1', 'type': 'written', 'stem': '说明主动回忆的机制和用途。', 'options': [], 'answer': ['主动提取记忆以检验理解。'],
                'rubric': ['解释主动提取机制', '说明检验理解的用途'], 'explanation': '主动回忆通过提取检验理解。', 'knowledge_point': '主动回忆', 'difficulty': 'easy'}
ANSWER = '主动提取记忆，检验理解。'
VERDICT = {'criteria': [{'index': 0, 'met': True, 'quote': '主动提取记忆', 'feedback': '覆盖机制'},
                        {'index': 1, 'met': True, 'quote': '检验理解', 'feedback': '覆盖用途'}],
               'contradiction': False, 'uncertain': False, 'feedback': '两个要点均已覆盖。'}


async def fixture(user):
    quiz = 'quiz_' + uuid.uuid4().hex
    await quizzes.save_quiz_session(quiz, user, 'Synthetic written practice', 'Deterministic test', 'Synthetic', [QUESTION])
    return quiz


async def checkpoint():
    context = TaskContext(await jobs.claim())
    await context.checkpoint('written_grade', {'output': [{'content': json.dumps(VERDICT), 'finish_reason': 'stop'}]})
    return context


@pytest.mark.asyncio
async def test_written_admission_idempotency_ownership_and_restart(users):
    quiz = await fixture(users[0])
    request = AnswerSubmission(question_id='q1', selected_answers=[ANSWER])
    a, b = await asyncio.gather(service.submit(quiz, users[0], request, 'device-one'), service.submit(quiz, users[0], request, 'device-two'))
    assert a['task_id'] == b['task_id']
    for _ in range(2):
        assert (await service.submit(quiz, users[0], request, 'device-two'))['task_id'] == a['task_id']
    with pytest.raises(HTTPException) as error:
        await service.submit(quiz, users[1], request, 'other-user')
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        await service.submit(quiz, users[0], AnswerSubmission(question_id='q1', selected_answers=['不同答案']), 'another-device')
    assert error.value.status_code == 409
    assert await get_attempts(quiz, users[0]) == []
    assert not {'answer', 'rubric', 'accepted_answers'} & public_quiz({'questions': [QUESTION]})['questions'][0].keys()
    context = await checkpoint()
    async with transaction() as cur:
        await cur.execute('UPDATE learning_jobs SET lease_until=UTC_TIMESTAMP()-INTERVAL 1 SECOND WHERE task_id=%s', (context.task_id,))
    restored = TaskContext(await jobs.claim())
    await service.run(restored)
    assert (await jobs.get_owned(context.task_id, users[0]))['status'] == 'completed'
    records = await get_attempts(quiz, users[0])
    assert len(records) == 1 and records[0]['is_correct']
    assert records[0]['grading']['method'] == 'model-rubric-v1'
    assert (await service.submit(quiz, users[0], request, 'new-device'))['completed']
    assert (await learning.summary(users[0]))['concepts'][0]['attempts'] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['cancel', 'publication'])
async def test_written_failure_never_partially_updates_attempt_or_learning(users, monkeypatch, failure):
    quiz = await fixture(users[0])
    request = AnswerSubmission(question_id='q1', selected_answers=[ANSWER])
    task = await service.submit(quiz, users[0], request, 'failed-example')
    context = await checkpoint()
    if failure == 'cancel':
        await jobs.cancel(task['task_id'], users[0])
    else:
        async def fail(*args):
            raise RuntimeError('Synthetic publication failure')
        monkeypatch.setattr(jobs, 'publish_result', fail)
    with pytest.raises((jobs.TaskLeaseLost, RuntimeError)):
        await service.run(context)
    assert await get_attempts(quiz, users[0]) == []
    assert (await learning.summary(users[0]))['concepts'] == []


@pytest.mark.asyncio
async def test_written_review_preserves_version_and_does_not_recharge_on_replay(users):
    quiz = await fixture(users[0])
    await service.submit(quiz, users[0], AnswerSubmission(question_id='q1', selected_answers=[ANSWER]), 'initial-answer')
    await service.run(await checkpoint())
    card = (await learning.cards(users[0], 'all'))[0]
    async with transaction() as cur:
        await cur.execute('UPDATE learning_cards SET due_at=UTC_TIMESTAMP()-INTERVAL 1 DAY WHERE card_id=%s', (card['card_id'],))
    request = learning.ReviewSubmission(version=card['version'], selected_answers=[ANSWER])
    await service.submit_review(card['card_id'], users[0], request, 'review-answer')
    await service.run(await checkpoint())
    event = await learning.review_result(card['card_id'], card['version'], users[0])
    assert event['record']['is_correct'] and event['version'] == card['version'] + 1
    assert (await service.submit_review(card['card_id'], users[0], request, 'another-review-key'))['completed']
    assert (await learning.summary(users[0]))['concepts'][0]['attempts'] == 2
