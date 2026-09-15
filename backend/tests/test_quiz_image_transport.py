import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from app.services import quiz_image_service as images
from fastapi import HTTPException


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [200, 302, 401, 403, 429, 500])
async def test_image_transport_uses_separate_key_exactly_one_image_and_no_retry(monkeypatch, status):
    settings = SimpleNamespace(dashscope_image_api_key='synthetic-image-only', dashscope_api_key='synthetic-embedding-only',
                               dashscope_base_url='https://dashscope.aliyuncs.com/compatible-mode/v1', dashscope_image_base_url='',
                               dashscope_image_model='qwen-image-2.0', image_gen_size='1024*1024')
    monkeypatch.setattr(images, 'require_config', lambda: settings)
    seen = []
    def respond(request):
        seen.append(request)
        assert request.headers['Authorization'] == 'Bearer synthetic-image-only'
        assert str(request.url).endswith('/api/v1/services/aigc/multimodal-generation/generation')
        payload = json.loads(request.content)
        assert payload['parameters'] == {'n': 1, 'size': '1024*1024', 'prompt_extend': False, 'watermark': False, 'negative_prompt': images.NEGATIVE_PROMPT}
        return httpx.Response(status, json={'output': {'choices': [{'finish_reason': 'stop', 'message': {'content': [{'image': 'https://public.example/image.png'}]}}]}},
                              headers={'Location': 'http://127.0.0.1/private'})
    factory = httpx.AsyncClient
    def client(**kwargs):
        assert kwargs['follow_redirects'] is False and kwargs['trust_env'] is False and kwargs['timeout'] == 35
        return factory(transport=httpx.MockTransport(respond), **kwargs)
    monkeypatch.setattr(images.httpx, 'AsyncClient', client)
    if status == 200:
        result, tokens = await images.generate('Public synthetic diagram')
        assert result['image_count'] == 1 and tokens is None
    else:
        with pytest.raises(HTTPException) as error:
            await images.generate('Public synthetic diagram')
        assert error.value.status_code == (503 if status in (401, 403) else 429 if status == 429 else 502)
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_storage_privacy_failure_stops_before_paid_image_generation(monkeypatch):
    context = SimpleNamespace(user_id=12, payload={'quiz_id': 'quiz_fixture', 'doc_ids': [], 'scope': []},
                              checkpoints={}, external=AsyncMock(), checkpoint=AsyncMock())
    row = {'asset_id': 'asset_fixture', 'object_key': 'fixture', 'question_id': 'q1'}
    monkeypatch.setattr(images.assets, 'for_task', AsyncMock(return_value=[row]))
    monkeypatch.setattr(images.assets, 'reserve', AsyncMock(return_value=row))
    monkeypatch.setattr(images.assets, 'finish', AsyncMock(return_value={'image_count': 0}))
    monkeypatch.setattr(images.quiz_repository, 'get_quiz_detail', AsyncMock(return_value={'questions': [{'id': 'q1'}]}))
    monkeypatch.setattr(images, 'require_config', lambda: None)
    monkeypatch.setattr(images.storage, 'verify_storage', AsyncMock(side_effect=ValueError('Anonymous object access is not denied')))
    assert (await images.run(context))['image_count'] == 0
    context.external.assert_not_awaited()
    assert context.checkpoint.await_args.args[1]['state'] == 'failed'
