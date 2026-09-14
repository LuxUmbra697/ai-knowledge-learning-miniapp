"""Private practice admission, response recovery and non-disclosing compatibility polling."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from app.llm import quiz_chain
from app.models.quiz import QuizGenerateRequest
from app.repositories import job_repository as jobs
from app.services import quiz_service, quiz_task_service as service


@pytest.mark.parametrize('change', [{'user_id': 999}, {'is_correct': True}, {'doc_id': ''}, {'user_input': '   '}])
def test_quiz_admission_rejects_identity_grading_and_empty_private_scope(change):
    with pytest.raises(ValidationError):
        QuizGenerateRequest.model_validate({'user_input': 'Practice', 'doc_id': 'doc_owned', **change})


@pytest.mark.asyncio
async def test_private_text_quiz_uses_durable_admission_only(monkeypatch):
    enqueue = AsyncMock(return_value={'task_id': 'job_' + 'a' * 32})
    monkeypatch.setattr(service, 'create', enqueue)
    legacy = AsyncMock(); monkeypatch.setattr(quiz_service.task_repository, 'create_task', legacy)
    req = QuizGenerateRequest(user_input='Private practice', doc_id='doc_owned')
    result = await quiz_service.create_quiz_task(req, 12, key='synthetic-key')
    assert result.task_id.startswith('job_')
    enqueue.assert_awaited_once_with(req, 12, 'synthetic-key')
    legacy.assert_not_awaited()


@pytest.mark.asyncio
async def test_admission_captures_server_scope_and_rejects_other_owner(monkeypatch):
    rows = [{'doc_id': 'doc_owned', 'revision': 2, 'index_version': 'v1'}]
    scoped = AsyncMock(return_value=rows)
    monkeypatch.setattr(service.index, 'scoped_chunks', scoped)
    monkeypatch.setattr(service.vectors, 'index_version', lambda: 'v1')
    enqueue = AsyncMock(return_value={'task_id': 'job_test'})
    monkeypatch.setattr(jobs, 'enqueue', enqueue)
    req = QuizGenerateRequest(user_input='Private practice', doc_id='doc_owned')
    await service.create(req, 12, 'synthetic-key')
    assert enqueue.await_args.args[:2] == (12, 'quiz')
    payload = enqueue.await_args.args[2]
    assert payload['scope'] == [['doc_owned', 2, 'v1']]
    assert 'user_id' not in payload and 'questions' not in payload
    scoped.side_effect = HTTPException(404, 'Not owned')
    with pytest.raises(HTTPException):
        await service.create(req, 13, 'synthetic-key')
    assert enqueue.await_count == 1


@pytest.mark.asyncio
async def test_quiz_checkpoint_validates_without_initializing_model(monkeypatch, sample_quiz_response_data):
    data = {key: sample_quiz_response_data[key] for key in ('title', 'summary', 'questions')}
    context = SimpleNamespace(checkpoints={'quiz': {'output': [{'content': json.dumps(data), 'finish_reason': 'stop'}]}}, external=AsyncMock())
    factory = Mock(side_effect=AssertionError('Recovery must not initialize a model'))
    monkeypatch.setattr(quiz_chain, 'get_chat_model', factory)
    result = await quiz_chain.generate_quiz('Recovery', 5, context=context, private_source=True, search_context='Synthetic source')
    assert len(result.questions) == 5
    factory.assert_not_called()
    context.external.assert_not_awaited()


@pytest.mark.asyncio
async def test_compatibility_poll_rejects_wrong_kind_and_maps_cancellation(monkeypatch):
    get = AsyncMock(return_value={'kind': 'report', 'status': 'completed', 'result': {}})
    monkeypatch.setattr(jobs, 'get_owned', get)
    with pytest.raises(HTTPException) as error:
        await service.status('job_' + 'a' * 32, 12)
    assert error.value.status_code == 404
    get.return_value = {'kind': 'quiz', 'status': 'cancelled', 'stage': 'cancelled', 'result': None, 'error_message': None}
    result = await service.status('job_' + 'a' * 32, 12)
    assert result.status == 'failed' and result.result is None and result.error_message
