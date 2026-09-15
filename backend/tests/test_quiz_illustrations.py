from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from app.models.quiz import QuizGenerateRequest
from app.services import quiz_service, quiz_task_service
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_illustrated_practice_admission_never_uses_process_local_execution(monkeypatch):
    monkeypatch.setattr(quiz_task_service, 'create', AsyncMock(return_value={'task_id': 'job_images'}))
    old = AsyncMock(side_effect=AssertionError('Process-local task is forbidden'))
    monkeypatch.setattr(quiz_service.task_repository, 'create_task', old)
    task = await quiz_service.create_quiz_task(QuizGenerateRequest(user_input='Public topic', generate_images=True), 12, 'image-request-key')
    assert task.task_id == 'job_images'
    old.assert_not_awaited()


def test_image_transport_requires_its_own_key_and_a_native_https_endpoint(monkeypatch):
    from app.services import quiz_image_service as images
    settings = images.get_settings().model_copy(update={'dashscope_image_api_key': '', 'dashscope_api_key': 'synthetic-embedding-only'})
    monkeypatch.setattr(images, 'get_settings', lambda: settings)
    with pytest.raises(HTTPException) as error:
        images.require_config()
    assert error.value.status_code == 422
    assert images.image_endpoint('https://dashscope.aliyuncs.com/compatible-mode/v1', '') == 'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation'
    for base in ('http://example.org/api/v1', 'https://example.org/compatible-mode/v1?key=secret', 'https://user:secret@example.org/api/v1'):
        with pytest.raises(ValueError):
            images.image_endpoint('', base)


@pytest.mark.asyncio
async def test_saved_image_response_is_not_regenerated_when_storage_is_retried(monkeypatch):
    from app.services import quiz_image_service as images
    context = SimpleNamespace(user_id=12, task_id='job_' + 'a' * 32, lease_token='lease',
                              payload={'quiz_id': 'quiz_' + 'b' * 32, 'doc_ids': [], 'scope': [], 'asset_ids': ['asset_' + 'c' * 32]},
                              checkpoints={'image_1': {'output': {'url': 'https://public.example/temporary.png'}}}, external=AsyncMock(), checkpoint=AsyncMock())
    asset = {'asset_id': 'asset_' + 'c' * 32, 'question_id': 'q1', 'object_key': 'synthetic-private/asset.jpg', 'state': 'reserved'}
    monkeypatch.setattr(images.assets, 'for_task', AsyncMock(return_value=[asset]))
    monkeypatch.setattr(images.assets, 'reserve', AsyncMock(return_value=asset))
    monkeypatch.setattr(images.assets, 'finish', AsyncMock(return_value={'quiz_id': context.payload['quiz_id'], 'image_count': 1}))
    monkeypatch.setattr(images.quiz_repository, 'get_quiz_detail', AsyncMock(return_value={'questions': [{'id': 'q1', 'stem': 'Synthetic topic', 'knowledge_point': 'Fixture'}]}))
    monkeypatch.setattr(images, 'require_config', Mock())
    monkeypatch.setattr(images, 'persist_image', AsyncMock(return_value={'asset_id': asset['asset_id'], 'state': 'ready', 'width': 512, 'height': 512, 'size_bytes': 1000}))
    result = await images.run(context)
    assert result['image_count'] == 1
    context.external.assert_not_awaited()
    images.persist_image.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancelled_image_task_never_publishes_even_a_cached_image(monkeypatch):
    from app.repositories.job_repository import TaskLeaseLost
    from app.services import quiz_image_service as images
    context = SimpleNamespace(user_id=12, payload={'doc_ids': [], 'scope': []})
    monkeypatch.setattr(images.assets, 'for_task', AsyncMock(side_effect=TaskLeaseLost()))
    persist = AsyncMock(); monkeypatch.setattr(images, 'persist_image', persist)
    with pytest.raises(TaskLeaseLost):
        await images.run(context)
    persist.assert_not_awaited()
