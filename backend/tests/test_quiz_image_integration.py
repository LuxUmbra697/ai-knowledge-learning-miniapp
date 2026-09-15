"""Illustration API contracts; persistence and failure isolation also run against real MySQL."""
from unittest.mock import AsyncMock

import pytest

from app.models.quiz import QuizGenerateRequest, QuizOutput
from app.services import quiz_service, quiz_image_service


@pytest.mark.asyncio
async def test_generate_images_false_skips_image_service(monkeypatch, durable_quiz_transport, sample_quiz_response_data):
    output = QuizOutput.model_validate(sample_quiz_response_data)
    queue = durable_quiz_transport(output)
    generation = AsyncMock()
    monkeypatch.setattr(quiz_image_service, 'generate', generation)
    request = QuizGenerateRequest(user_input='Synthetic public topic', generate_images=False)
    result = await quiz_service.handle_quiz_generate(request, user_id=1)
    queue.create.assert_awaited_once_with(request, 1, None)
    generation.assert_not_awaited()
    assert result.image_notice is None
    assert all(question.image_url is None and question.image_asset_id is None for question in result.questions)


@pytest.mark.asyncio
async def test_generate_images_true_returns_an_owned_asset_reference_not_a_permanent_public_url(durable_quiz_transport, sample_quiz_response_data):
    output = QuizOutput.model_validate(sample_quiz_response_data)
    output.questions[0].image_asset_id = 'asset_' + 'a' * 32
    queue = durable_quiz_transport(output)
    queue.restore.return_value.image_notice = '配图任务已安排，文字练习可以先开始。'
    request = QuizGenerateRequest(user_input='Synthetic illustrated topic', generate_images=True)
    result = await quiz_service.handle_quiz_generate(request, user_id=1)
    queue.create.assert_awaited_once_with(request, 1, None)
    assert result.questions[0].image_asset_id == output.questions[0].image_asset_id
    assert all(question.image_url is None for question in result.questions)
    assert result.image_notice


@pytest.mark.asyncio
async def test_failed_image_job_returns_actionable_state_without_signing_storage(monkeypatch):
    monkeypatch.setattr(quiz_image_service.assets, 'get_owned', AsyncMock(return_value={
        'asset_id': 'asset_fixture', 'state': 'reserved', 'job_status': 'failed', 'task_id': 'job_fixture', 'job_stage': 'failed',
    }))
    sign = AsyncMock()
    monkeypatch.setattr(quiz_image_service.storage, 'signed_url', sign)
    result = await quiz_image_service.get_image('asset_fixture', 1)
    assert result['status'] == 'failed' and result['url'] is None
    assert '文字练习不受影响' in result['message']
    sign.assert_not_called()


@pytest.mark.asyncio
async def test_unanswered_question_never_receives_a_signed_illustration(monkeypatch):
    monkeypatch.setattr(quiz_image_service.assets, 'get_owned', AsyncMock(return_value={
        'asset_id': 'asset_fixture', 'state': 'ready', 'job_status': 'completed', 'task_id': 'job_fixture',
        'job_stage': 'completed', 'object_key': 'fixture.jpg', 'answered': False,
    }))
    from unittest.mock import Mock
    sign = Mock(return_value='https://private.example/signed')
    monkeypatch.setattr(quiz_image_service.storage, 'signed_url', sign)
    result = await quiz_image_service.get_image('asset_fixture', 1)
    assert result['status'] == 'locked' and result['url'] is None
    sign.assert_not_called()
