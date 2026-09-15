import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException
import pytest

from app.llm import report_chain
from app.models.quiz import Question
from app.models.report import ReportGenerateRequest
from app.models.report import ReportOutput
from app.services import report_service as service


@pytest.mark.asyncio
async def test_report_admission_never_queues_an_unowned_or_incomplete_quiz(monkeypatch):
    enqueue = AsyncMock()
    monkeypatch.setattr(service.jobs, 'enqueue', enqueue)
    detail = AsyncMock(return_value=None)
    monkeypatch.setattr(service.quiz_repository, 'get_quiz_detail', detail)
    with pytest.raises(HTTPException) as error:
        await service.create_report_task(ReportGenerateRequest(quiz_id='other'), 1, 'request-key')
    assert error.value.status_code == 404
    detail.return_value = {'title': 'quiz', 'questions': [{'id': 'q1'}]}
    monkeypatch.setattr(service, 'get_attempts', AsyncMock(return_value=[]))
    with pytest.raises(HTTPException) as error:
        await service.create_report_task(ReportGenerateRequest(quiz_id='own'), 1, 'request-key')
    assert error.value.status_code == 409
    enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_report_admission_payload_uses_only_owned_server_input(monkeypatch):
    monkeypatch.setattr(service.quiz_repository, 'get_quiz_detail', AsyncMock(return_value={'title': 'stored title', 'questions': [{'id': 'q1'}]}))
    monkeypatch.setattr(service, 'get_attempts', AsyncMock(return_value=[{'question_id': 'q1'}]))
    enqueue = AsyncMock(return_value={'task_id': 'job_test'})
    monkeypatch.setattr(service.jobs, 'enqueue', enqueue)
    request = ReportGenerateRequest(quiz_id='own', topic='untrusted topic')
    await service.create_report_task(request, 7, 'request-key')
    assert enqueue.await_args.args == (7, 'report', {'quiz_id': 'own', 'title': 'stored title'}, 'request-key')


@pytest.mark.asyncio
async def test_saved_legacy_report_does_not_require_new_attempt_rows(monkeypatch):
    detail = {'title': 'legacy report', 'questions': [{'id': 'old'}], 'report': {'accuracy': 80}}
    monkeypatch.setattr(service.quiz_repository, 'get_quiz_detail', AsyncMock(return_value=detail))
    monkeypatch.setattr(service, 'get_attempts', AsyncMock(return_value=[]))
    assert await service.report_inputs(ReportGenerateRequest(quiz_id='legacy'), 1) == (detail, [])


@pytest.mark.asyncio
async def test_restored_report_response_does_not_require_model_credentials(monkeypatch, sample_quiz_response_data):
    report = {'accuracy': 99, 'mastered_points': [], 'weak_points': [], 'three_line_summary': ['A', 'B', 'C'],
              'advice': ['Review the source'], 'share_quote': 'Keep learning'}
    context = SimpleNamespace(checkpoints={'report': {'output': [{'content': json.dumps(report), 'finish_reason': 'stop'}]}})
    def unexpected_model(**_kwargs):
        raise AssertionError('Restoration must not initialize a provider client')
    monkeypatch.setattr(report_chain, 'get_chat_model', unexpected_model)
    result = await report_chain.generate_report('quiz', [Question.model_validate(q) for q in sample_quiz_response_data['questions']], [],
                                                 {'accuracy': 20}, context=context)
    assert result.accuracy == 20


@pytest.mark.asyncio
async def test_worker_grades_owned_records_and_publishes_with_its_lease(monkeypatch, sample_report_request):
    monkeypatch.setattr(service.quiz_repository, 'get_quiz_detail', AsyncMock(return_value={
        'title': 'stored title', 'questions': sample_report_request['questions']}))
    monkeypatch.setattr(service, 'get_attempts', AsyncMock(return_value=sample_report_request['answer_records']))
    output = ReportOutput(accuracy=100, mastered_points=[], weak_points=[], three_line_summary=['A', 'B', 'C'], advice=['Review'], share_quote='Study')
    generated = AsyncMock(return_value=output)
    monkeypatch.setattr(service, 'generate_report', generated)
    context = SimpleNamespace(payload={'quiz_id': 'owned'}, user_id=7, checkpoint=AsyncMock())
    complete = AsyncMock(side_effect=lambda quiz_id, user_id, records, score, report, context: report)
    monkeypatch.setattr(service.quiz_repository, 'complete_quiz', complete)
    result = await service.run_report_task(context)
    assert generated.await_args.kwargs['topic'] == 'stored title'
    assert generated.await_args.kwargs['score_summary']['correct'] == 4
    assert generated.await_args.kwargs['context'] is context
    assert complete.await_args.args[1] == 7 and complete.await_args.kwargs['context'] is context
    assert result['accuracy'] == 80
