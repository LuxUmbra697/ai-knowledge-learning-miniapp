"""Real isolated MySQL: report deduplication, cancellation, checkpoint recovery and atomic XP."""
import json
import uuid

from fastapi import HTTPException
import pytest

from app.models.report import ReportGenerateRequest
from app.repositories import job_repository as jobs, quiz_repository
from app.repositories.rag_index_repository import transaction
from app.services import report_service
from app.services.grading_service import AnswerSubmission, submit_question
from app.worker import TaskContext


REPORT = {'accuracy': 100, 'mastered_points': ['review'], 'weak_points': [], 'three_line_summary': ['A', 'B', 'C'],
          'advice': ['Review the source'], 'share_quote': 'Keep learning'}


async def completed_practice(user):
    quiz_id = 'quiz_test_' + uuid.uuid4().hex
    question = dict(id='q1', type='single', stem='Synthetic report fixture', options=[{'key': 'A', 'text': 'Yes'}, {'key': 'B', 'text': 'No'}],
                    answer=['A'], explanation='Synthetic explanation', knowledge_point='review', difficulty='easy')
    await quiz_repository.save_quiz_session(quiz_id, user, 'Synthetic report', '', '', [question])
    await submit_question(quiz_id, user, AnswerSubmission(question_id='q1', selected_answers=['A']))
    return quiz_id


async def status(user, quiz_id):
    async with transaction() as cur:
        await cur.execute('SELECT total_xp FROM users WHERE id=%s', (user,))
        xp = (await cur.fetchone())['total_xp']
        await cur.execute('SELECT COUNT(*) AS n FROM reports WHERE quiz_id=%s', (quiz_id,))
        reports = (await cur.fetchone())['n']
        await cur.execute('SELECT COUNT(*) AS n FROM answer_records WHERE quiz_id=%s', (quiz_id,))
        records = (await cur.fetchone())['n']
    return xp, reports, records


@pytest.mark.asyncio
async def test_report_restores_known_response_and_commits_result_xp_and_job_once(users):
    quiz_id = await completed_practice(users[0])
    request = ReportGenerateRequest(quiz_id=quiz_id)
    task = await report_service.create_report_task(request, users[0], uuid.uuid4().hex)
    duplicate = await report_service.create_report_task(request, users[0], uuid.uuid4().hex)
    assert task['task_id'] == duplicate['task_id']
    with pytest.raises(HTTPException) as error:
        await report_service.create_report_task(request, users[1], uuid.uuid4().hex)
    assert error.value.status_code == 404
    claim = await jobs.claim()
    await jobs.reserve_call(claim['task_id'], claim['lease_token'], 'report')
    await jobs.complete_call(claim['task_id'], claim['lease_token'], 'report',
                             {'output': [{'content': json.dumps(REPORT), 'finish_reason': 'stop'}]}, 10)
    async with transaction() as cur:
        await cur.execute('UPDATE learning_jobs SET lease_until=UTC_TIMESTAMP()-INTERVAL 1 SECOND WHERE task_id=%s', (claim['task_id'],))
    restored = TaskContext(await jobs.claim())
    assert await report_service.run_report_task(restored) == REPORT
    assert await status(users[0], quiz_id) == (12, 1, 1)
    saved = await jobs.get_owned(task['task_id'], users[0])
    assert saved['status'] == 'completed' and saved['result'] == REPORT and saved['trace']['model_calls'] == 1
    replay = await report_service.create_report_task(request, users[0], uuid.uuid4().hex)
    assert replay['task_id'] == task['task_id'] and replay['replayed']
    assert await status(users[0], quiz_id) == (12, 1, 1)


@pytest.mark.asyncio
async def test_cancelled_report_cannot_commit_any_learning_side_effect(users):
    quiz_id = await completed_practice(users[0])
    task = await report_service.create_report_task(ReportGenerateRequest(quiz_id=quiz_id), users[0], uuid.uuid4().hex)
    context = TaskContext(await jobs.claim())
    await jobs.cancel(task['task_id'], users[0])
    with pytest.raises(jobs.TaskLeaseLost):
        await quiz_repository.complete_quiz(quiz_id, users[0], [], {'correct': 1, 'total': 1, 'accuracy': 100}, REPORT, context=context)
    assert await status(users[0], quiz_id) == (0, 0, 0)


@pytest.mark.asyncio
async def test_report_publication_rolls_back_if_final_task_update_fails(users, monkeypatch):
    quiz_id = await completed_practice(users[0])
    await report_service.create_report_task(ReportGenerateRequest(quiz_id=quiz_id), users[0], uuid.uuid4().hex)
    context = TaskContext(await jobs.claim())
    async def fail(*_args):
        raise RuntimeError('Synthetic final write failure')
    monkeypatch.setattr(jobs, 'publish_result', fail)
    with pytest.raises(RuntimeError):
        await quiz_repository.complete_quiz(quiz_id, users[0], [], {'correct': 1, 'total': 1, 'accuracy': 100}, REPORT, context=context)
    assert await status(users[0], quiz_id) == (0, 0, 0)
    assert (await jobs.get_owned(context.task_id, users[0]))['status'] == 'running'
