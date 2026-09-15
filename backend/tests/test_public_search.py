import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from app.services import public_search_service as search
from fastapi import HTTPException


def test_public_sources_are_bounded_and_never_accept_active_or_private_urls():
    for url in ('javascript:alert(1)', 'https://127.0.0.1/a', 'https://[::1]/', 'https://metadata.internal/', 'https://user:password@example.org/', 'http://example.org/'):
        assert search.safe_source_url(url) is None
    source = search.normalize_results({'results': [{'url': 'https://docs.python.org/3/', 'title': 't' * 300, 'content': 'c' * 3000}] * 10})
    assert len(source['sources']) == 1
    assert len(source['sources'][0]['excerpt']) == 1000 and len(source['sources'][0]['title']) == 160
    assert source['verification'] == 'reference_only_not_question_level_verified'


@pytest.mark.asyncio
async def test_private_scopes_rejected_before_configuration_or_external_call():
    context = SimpleNamespace(payload={'doc_ids': ['owned-doc'], 'query': 'private text'}, external=AsyncMock())
    with pytest.raises(HTTPException) as error:
        await search.fetch_context(context)
    assert error.value.status_code == 422
    context.external.assert_not_awaited()


@pytest.mark.asyncio
async def test_saved_web_sources_resume_without_another_search(monkeypatch):
    saved = search.normalize_results({'results': [{'url': 'https://docs.python.org/3/', 'title': 'Python', 'content': 'List reference'}]})
    monkeypatch.setattr(search, 'require_available', lambda: pytest.fail('A saved search must not need a provider key'))
    context = SimpleNamespace(payload={'doc_ids': [], 'scope': []}, checkpoints={'public_search': {'output': saved}}, external=AsyncMock())
    assert json.loads(await search.fetch_context(context)) == saved
    context.external.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['timeout', 'unauthorized', 'empty'])
async def test_search_failure_does_not_silently_become_grounded_generation(monkeypatch, outcome):
    settings = SimpleNamespace(tavily_api_key='synthetic')
    monkeypatch.setattr(search, 'require_available', lambda: settings)
    remote = AsyncMock(side_effect=TimeoutError() if outcome == 'timeout' else HTTPException(503, 'unavailable') if outcome == 'unauthorized' else None,
                       return_value=(search.normalize_results({'results': []}), None))
    monkeypatch.setattr(search, '_search', remote)
    async def external(_stage, operation, _bytes):
        result, _ = await operation()
        return result
    context = SimpleNamespace(payload={'doc_ids': [], 'query': 'public query'}, checkpoints={}, external=AsyncMock(side_effect=external))
    with pytest.raises(HTTPException) as error:
        await search.fetch_context(context)
    assert error.value.status_code == {'timeout': 504, 'unauthorized': 503, 'empty': 422}[outcome]
    remote.assert_awaited_once()
    assert context.external.await_args.args[0] == 'public_search'


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [200, 302, 401, 429, 500])
async def test_search_transport_is_fixed_bounded_and_does_not_follow_redirects(monkeypatch, status):
    seen = []
    def respond(request):
        seen.append(request)
        assert str(request.url) == search.ENDPOINT
        payload = json.loads(request.content)
        assert payload['query'] == 'public topic'
        assert payload['max_results'] == 3 and payload['search_depth'] == 'basic'
        assert not any(payload[key] for key in ('auto_parameters', 'include_answer', 'include_raw_content', 'include_images'))
        return httpx.Response(status, json={'results': []}, headers={'Location': 'http://127.0.0.1/private'})
    factory = httpx.AsyncClient
    def client(**kwargs):
        assert kwargs['follow_redirects'] is False and kwargs['trust_env'] is False and kwargs['timeout'] == 15
        return factory(transport=httpx.MockTransport(respond), **kwargs)
    monkeypatch.setattr(search.httpx, 'AsyncClient', client)
    if status == 200:
        result, tokens = await search._search('public topic', SimpleNamespace(tavily_api_key='synthetic'))
        assert result['status'] == 'no_results' and tokens is None
    else:
        with pytest.raises(HTTPException):
            await search._search('public topic', SimpleNamespace(tavily_api_key='synthetic'))
    assert len(seen) == 1
