from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.api.v1.routes import identity
from app.core.auth import get_current_user


@pytest.mark.asyncio
@pytest.mark.parametrize('path,payload', [
    ('qr/create', {'purpose': 'bind', 'user_id': 9}),
    ('qr/scan', {'scene': 'a' * 32, 'code': 'valid', 'openid': 'forged'}),
    ('wechat/finish', {'ticket': 'a' * 32 + '.' + 'b' * 43, 'action': 'register', 'user_id': 9}),
    ('password/reset', {'username': 'test', 'password': 'secret', 'recovery_code': 'private-recovery'}),
])
async def test_identity_inputs_reject_forgery_without_reflecting_secrets(path, payload):
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/api/v1/user/identity/' + path, json=payload)
    assert response.status_code == 422
    for secret in ('private-recovery', 'forged', 'secret'):
        assert secret not in response.text


@pytest.mark.asyncio
async def test_binding_requires_authentication_before_provider_call(monkeypatch):
    provider = AsyncMock()
    monkeypatch.setattr(identity.wechat_qr, 'qr_image', provider)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/api/v1/user/identity/qr/bind', json={'password': 'test-private-password'})
    assert response.status_code == 401
    provider.assert_not_called()


@pytest.mark.asyncio
async def test_direct_native_binding_uses_authenticated_user_and_verified_code(monkeypatch):
    provider = AsyncMock(return_value='verified-openid')
    bind = AsyncMock(return_value={'status': 'bound'})
    monkeypatch.setattr(identity, 'wx_code_to_openid', provider)
    monkeypatch.setattr(identity.service, 'direct_bind', bind)
    monkeypatch.setattr(identity, 'rate', AsyncMock())
    app.dependency_overrides[get_current_user] = lambda: 7
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post('/api/v1/user/identity/wechat/bind-current', json={'wechat_code': 'fresh-code', 'password': 'private-password'})
            assert response.status_code == 200
            bind.assert_awaited_once_with(7, 'verified-openid', password='private-password')
            response = await client.post('/api/v1/user/identity/wechat/bind-current', json={'wechat_code': 'fresh-code', 'password': 'private-password', 'user_id': 8})
            assert response.status_code == 422
            assert 'private-password' not in response.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_native_binding_never_exchanges_code_without_login(monkeypatch):
    provider = AsyncMock()
    monkeypatch.setattr(identity, 'wx_code_to_openid', provider)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/api/v1/user/identity/wechat/bind-current', json={'wechat_code': 'code', 'password': 'private-password'})
    assert response.status_code == 401
    provider.assert_not_called()
