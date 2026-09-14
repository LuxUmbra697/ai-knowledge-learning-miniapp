import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.quiz import QuizGenerateRequest, QuizOutput
from app.core.exceptions import QuizGenerationError
from app.llm import quiz_chain, langchain_factory
from app.services import quiz_service
from app.repositories import quiz_repository, task_repository
from fastapi import HTTPException


def output(sample_quiz_response_data):
    return {key: copy.deepcopy(sample_quiz_response_data[key]) for key in ('title', 'summary', 'questions')}


@pytest.mark.parametrize('corruption', ['count', 'id', 'blank_id', 'long_id', 'option_key', 'duplicate_option', 'answer_key', 'multiple', 'judge', 'empty', 'image'])
def test_generated_question_contract_rejects_invalid_exercises(sample_quiz_response_data, corruption):
    data = output(sample_quiz_response_data)
    if corruption == 'count': data['questions'].pop()
    elif corruption == 'id': data['questions'][1]['id'] = 'q1'
    elif corruption == 'blank_id': data['questions'][0]['id'] = ' '
    elif corruption == 'long_id': data['questions'][0]['id'] = 'q' * 65
    elif corruption == 'option_key': data['questions'][0]['options'][1]['key'] = 'A'
    elif corruption == 'duplicate_option': data['questions'][0]['options'][1]['text'] = data['questions'][0]['options'][0]['text']
    elif corruption == 'answer_key': data['questions'][0]['answer'] = ['Z']
    elif corruption == 'multiple': data['questions'][3]['answer'] = ['A']
    elif corruption == 'judge': data['questions'][4]['options'][0]['text'] = 'not a judgment option'
    elif corruption == 'empty': data['questions'][0]['knowledge_point'] = ' '
    elif corruption == 'image': data['questions'][0]['image_url'] = 'http://127.0.0.1/private'
    with pytest.raises(ValueError):
        quiz_chain.validate_quiz(data, 5, 'mixed')


def test_valid_exercise_preserves_all_three_question_types(sample_quiz_response_data):
    result = quiz_chain.validate_quiz(output(sample_quiz_response_data), 5, 'mixed')
    assert {q.type for q in result.questions} == {'single', 'multiple', 'judge'}


@pytest.mark.asyncio
async def test_sync_generation_does_not_succeed_when_storage_fails(monkeypatch, sample_quiz_response_data):
    monkeypatch.setattr(quiz_service, '_fetch_context', AsyncMock(return_value=''))
    monkeypatch.setattr(quiz_service, 'generate_quiz', AsyncMock(return_value=QuizOutput.model_validate(output(sample_quiz_response_data))))
    monkeypatch.setattr(quiz_service.quiz_repository, 'save_quiz_session', AsyncMock(side_effect=RuntimeError('private database diagnostic')))
    with pytest.raises(QuizGenerationError) as error:
        await quiz_service.handle_quiz_generate(QuizGenerateRequest(user_input='RAG basics'), user_id=1)
    assert 'private database diagnostic' not in str(error.value)


@pytest.mark.asyncio
async def test_async_generation_does_not_publish_unsaved_quiz(monkeypatch, sample_quiz_response_data):
    monkeypatch.setattr(quiz_service, '_fetch_context', AsyncMock(return_value=''))
    monkeypatch.setattr(quiz_service, 'generate_quiz', AsyncMock(return_value=QuizOutput.model_validate(output(sample_quiz_response_data))))
    monkeypatch.setattr(quiz_service.quiz_repository, 'save_quiz_session', AsyncMock(side_effect=RuntimeError('private database diagnostic')))
    update = AsyncMock(); monkeypatch.setattr(quiz_service.task_repository, 'update_task_status', update)
    await quiz_service._run_quiz_task('task_test', QuizGenerateRequest(user_input='RAG basics'), 1)
    assert [call.args[1] for call in update.await_args_list] == ['running', 'failed']
    assert 'private database diagnostic' not in str(update.await_args_list)


def test_shared_model_factory_disables_hidden_retries(monkeypatch):
    factory = lambda **kwargs: SimpleNamespace(**kwargs)
    monkeypatch.setattr(langchain_factory, 'ChatOpenAI', factory)
    settings = langchain_factory.get_settings().model_copy(update={'deepseek_api_key': 'synthetic-test-key'})
    monkeypatch.setattr(langchain_factory, 'get_settings', lambda: settings)
    langchain_factory.get_chat_model.cache_clear()
    try:
        model = langchain_factory.get_chat_model()
        assert model.max_retries == 0 and model.timeout == 20
    finally:
        langchain_factory.get_chat_model.cache_clear()


def test_empty_provider_key_cannot_fall_back_to_unrelated_environment_credentials(monkeypatch):
    settings = langchain_factory.get_settings().model_copy(update={'deepseek_api_key': ''})
    monkeypatch.setattr(langchain_factory, 'get_settings', lambda: settings)
    monkeypatch.setenv('OPENAI_API_KEY', 'unrelated-synthetic-key')
    langchain_factory.get_chat_model.cache_clear()
    try:
        with pytest.raises(ValueError, match='DEEPSEEK_API_KEY'):
            langchain_factory.get_chat_model()
    finally:
        langchain_factory.get_chat_model.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize('repository,method,args', [
    (quiz_repository, 'save_quiz_session', ('quiz', 1, 'title', 'summary', 'input', [])),
    (quiz_repository, 'save_answer_record', ('quiz', 1, [], 1, 1, 100)),
    (quiz_repository, 'save_report', ('quiz', 1, {})),
    (task_repository, 'create_task', ('task', 1, 'input', 3, 'mixed')),
    (task_repository, 'update_task_status', ('task', 'failed')),
])
async def test_missing_pool_never_makes_write_look_successful(monkeypatch, repository, method, args):
    monkeypatch.setattr(repository, 'get_mysql_pool', lambda: None)
    with pytest.raises(HTTPException) as error:
        await getattr(repository, method)(*args)
    assert error.value.status_code == 503
