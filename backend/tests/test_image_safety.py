from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi import HTTPException
import pytest

from app.repositories import image_repository
from app.services import image_service
from tests.test_image_service import _make_question


def image_settings(monkeypatch, **changes):
    settings = image_service.get_settings().model_copy(update=changes)
    monkeypatch.setattr(image_service, 'get_settings', lambda: settings)
    return settings


def test_image_model_cannot_fall_back_to_embedding_key(monkeypatch):
    from dashscope import MultiModalConversation
    image_settings(monkeypatch, dashscope_image_api_key='', dashscope_api_key='synthetic-embedding-only')
    call = Mock(); monkeypatch.setattr(MultiModalConversation, 'call', call)
    with pytest.raises(ValueError, match='DASHSCOPE_IMAGE_API_KEY'):
        image_service._call_image_model_sync('Synthetic prompt')
    call.assert_not_called()


def test_image_model_uses_separate_key_and_derives_empty_base(monkeypatch):
    import dashscope
    from dashscope import MultiModalConversation
    image_settings(monkeypatch, dashscope_image_api_key='synthetic-image-key', dashscope_api_key='synthetic-embedding-key',
                   dashscope_image_base_url='', dashscope_base_url='https://dashscope.aliyuncs.com/compatible-mode/v1')
    monkeypatch.setattr(dashscope, 'base_http_api_url', 'https://unused.invalid')
    call = Mock(return_value=SimpleNamespace(status_code=200, output=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=[{'image': 'https://public.example/image.png'}]))])))
    monkeypatch.setattr(MultiModalConversation, 'call', call)
    image_service._call_image_model_sync('Synthetic prompt')
    assert call.call_args.kwargs['api_key'] == 'synthetic-image-key'
    assert dashscope.base_http_api_url == 'https://dashscope.aliyuncs.com/api/v1'


@pytest.mark.asyncio
async def test_unavailable_quota_does_not_enable_charged_image_generation(monkeypatch):
    monkeypatch.setattr(image_repository, 'get_today_usage_count', AsyncMock(side_effect=RuntimeError('private database diagnostic')))
    generate = AsyncMock(); monkeypatch.setattr(image_service, 'generate_image_for_question', generate)
    images, notice = await image_service.generate_images_for_quiz([_make_question('q1')], 1, 'quiz_test')
    assert images == {} and notice and 'private database diagnostic' not in notice
    generate.assert_not_called()


@pytest.mark.asyncio
async def test_missing_database_cannot_silently_disable_image_quota(monkeypatch):
    monkeypatch.setattr(image_repository, 'get_mysql_pool', lambda: None)
    with pytest.raises(HTTPException) as error:
        await image_repository.get_today_usage_count(1)
    assert error.value.status_code == 503
    with pytest.raises(HTTPException):
        await image_repository.log_image_generation(1, 'quiz', 'q1', 'https://public.example/image.png')


@pytest.mark.asyncio
async def test_missing_images_have_explicit_feedback(monkeypatch):
    monkeypatch.setattr(image_repository, 'get_today_usage_count', AsyncMock(return_value=0))
    monkeypatch.setattr(image_service, 'generate_image_for_question', AsyncMock(return_value=None))
    images, notice = await image_service.generate_images_for_quiz([_make_question('q1')], 1, 'quiz_test')
    assert images == {} and notice and '未完成' in notice


@pytest.mark.asyncio
async def test_image_download_rejects_private_addresses_before_any_socket():
    with pytest.raises(ValueError):
        await image_service._download_image('https://169.254.169.254/latest/meta-data/')
