"""Production boundaries, tested without provider credentials or a database."""
import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.config import Settings, allowed_origins, validate_runtime
from app.core.http_security import SecurityHeadersMiddleware, JsonBodyLimitsMiddleware
from app.core.static_site import H5StaticFiles
from app.api.v1.routes import health
from app.services import user_service
from app.core.exceptions import AuthenticationError


def production(**overrides):
    return Settings(_env_file=None, **dict(app_env='production', app_debug=False,
                    jwt_secret='x' * 48, **overrides))


def test_production_guards_and_optional_image_key():
    validate_runtime(production())
    for changes in ({'app_debug': True}, {'jwt_secret': 'change-me-in-production'},
                    {'mysql_auto_init': True}, {'require_paid_models': True}):
        settings = production().model_copy(update=changes)
        with pytest.raises(RuntimeError):
            validate_runtime(settings)
    validate_runtime(production(require_paid_models=True, deepseek_api_key='configured',
                                dashscope_api_key='configured', dashscope_image_base_url=''))


@pytest.mark.parametrize('origin', ['*', 'https://site.test/path', 'https://user:pass@site.test',
                                   'https://site.test?query=1', 'file:///tmp', 'null'])
def test_cors_rejects_non_origins(origin):
    with pytest.raises(RuntimeError):
        allowed_origins(Settings(_env_file=None, cors_origins=origin))


def test_cors_explicit_origins_only():
    assert allowed_origins(Settings(_env_file=None, cors_origins='https://site.test, http://localhost:18082')) == [
        'https://site.test', 'http://localhost:18082']


def test_static_fallback_never_masks_api_or_missing_assets(tmp_path):
    (tmp_path / 'index.html').write_text('<html>studio</html>', encoding='utf-8')
    (tmp_path / 'app.js').write_text('var ready = true;', encoding='utf-8')
    (tmp_path / '.env').write_text('PRIVATE', encoding='utf-8')
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    app.mount('/', H5StaticFiles(directory=str(tmp_path)))
    client = TestClient(app)
    for path in ('/', '/pages/home/index?from=share', '/learning/path/index'):
        response = client.get(path)
        assert response.status_code == 200
        assert 'studio' in response.text
        assert "default-src 'self'" in response.headers['content-security-policy']
        assert "connect-src 'self' blob:" in response.headers['content-security-policy']
        assert response.headers['x-frame-options'] == 'DENY'
    for path in ('/api/v1/not-found', '/api', '/missing.js', '/.env', '/unknown'):
        response = client.get(path)
        assert response.status_code == 404
        assert '<html>studio' not in response.text
    assert client.get('/app.js').status_code == 200
    assert client.get('/api/v1/not-found').headers['cache-control'] == 'no-store'


def test_json_limit_rejects_before_parsing_and_includes_security_headers():
    app = FastAPI()
    app.add_middleware(JsonBodyLimitsMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.post('/api/v1/sample')
    async def sample(request: Request):
        return await request.json()

    client = TestClient(app)
    response = client.post('/api/v1/sample', content=b' ' * (512 * 1024 + 1))
    assert response.status_code == 413
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert len(response.headers['x-request-id']) == 32
    assert client.post('/api/v1/sample', json={'ok': True}).json() == {'ok': True}


def test_oss_artwork_csp_allows_only_the_owned_image_origin(tmp_path):
    (tmp_path / 'index.html').write_text('<html>studio</html>', encoding='utf-8')
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    app.mount('/', H5StaticFiles(directory=str(tmp_path)))
    policy = TestClient(app).get('/').headers['content-security-policy']
    directives = {parts[0]: parts[1:] for item in policy.split(';') if (parts := item.split())}
    origin = 'https://ai-knowledge-learn.oss-cn-guangzhou.aliyuncs.com'
    assert origin in directives['img-src']
    assert not any(value in directives['img-src'] for value in ['*', 'https:', 'https://*.aliyuncs.com'])
    assert directives['script-src'] == ["'self'"]
    assert directives['connect-src'] == ["'self'", 'blob:']


@pytest.mark.asyncio
async def test_readiness_checks_database_and_worker(monkeypatch):
    app = FastAPI()
    app.include_router(health.router, prefix='/api/v1')
    monkeypatch.setattr(health, 'get_settings', lambda: Settings(_env_file=None, worker_enabled=True))
    probe = AsyncMock()
    monkeypatch.setattr(health, 'probe_database', probe)
    worker = asyncio.create_task(asyncio.sleep(3600))
    app.state.worker = worker
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            assert (await client.get('/api/v1/ready')).status_code == 200
            probe.side_effect = RuntimeError('sensitive-database-detail')
            response = await client.get('/api/v1/ready')
            assert response.status_code == 503
            assert 'sensitive' not in response.text
            assert (await client.get('/api/v1/health')).status_code == 200
            probe.side_effect = None
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
            assert (await client.get('/api/v1/ready')).status_code == 503
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('payload', [None, [], {'openid': ''}, {'openid': 3},
                                   {'errcode': 40029, 'errmsg': 'private-code-sentinel'}])
async def test_wechat_rejects_invalid_identity_without_logging_payload(monkeypatch, payload):
    monkeypatch.setattr(user_service, 'get_settings', lambda: Settings(
        _env_file=None, wechat_app_id='app', wechat_app_secret='private-key-sentinel'))
    client = AsyncMock()
    client.get.return_value = Mock(json=Mock(return_value=payload), raise_for_status=Mock())
    monkeypatch.setattr(user_service.httpx, 'AsyncClient', lambda **kwargs: client)
    client.__aenter__.return_value = client
    logger = Mock()
    monkeypatch.setattr(user_service, 'logger', logger)
    with pytest.raises(AuthenticationError):
        await user_service.wx_code_to_openid('private-code-sentinel')
    assert 'private-' not in str(logger.mock_calls)


@pytest.mark.asyncio
async def test_wechat_transport_error_and_unhandled_error_logs_are_redacted(monkeypatch):
    monkeypatch.setattr(user_service, 'get_settings', lambda: Settings(
        _env_file=None, wechat_app_id='app', wechat_app_secret='private-key-sentinel'))
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.side_effect = httpx.ConnectError('https://provider/?secret=private-key-sentinel')
    monkeypatch.setattr(user_service.httpx, 'AsyncClient', lambda **kwargs: client)
    logger = Mock()
    monkeypatch.setattr(user_service, 'logger', logger)
    with pytest.raises(AuthenticationError):
        await user_service.wx_code_to_openid('private-code-sentinel')
    assert 'private-' not in str(logger.mock_calls)
    assert 'exc_info=True' not in str(logger.mock_calls)

    from app import main
    monkeypatch.setattr(main, 'logger', logger)
    request = Request({'type': 'http', 'path': '/api/v1/test', 'method': 'GET', 'headers': [],
                       'state': {'trace_id': 'a' * 32}})
    response = await main.unhandled_exception_handler(request, RuntimeError('private-key-sentinel'))
    assert 'private-' not in str(logger.mock_calls)
    assert b'private-' not in response.body
    assert b'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' in response.body


@pytest.mark.asyncio
async def test_unhandled_route_exception_does_not_escape_to_uvicorn_traceback(monkeypatch):
    from app.main import app
    from app.core.auth import create_token
    monkeypatch.setattr(user_service, 'get_profile', AsyncMock(side_effect=RuntimeError('private-provider-url-sentinel')))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=True), base_url='http://test') as client:
        response = await client.get('/api/v1/user/profile', headers={'Authorization': 'Bearer ' + create_token(1, 'test')})
        assert response.status_code == 500
        assert 'private-provider-url-sentinel' not in response.text
        assert response.headers['x-request-id'] in response.text
