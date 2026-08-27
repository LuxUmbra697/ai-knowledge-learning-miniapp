"""JWT 鉴权模块单元测试"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import jwt
import pytest

from app.core.auth import create_token, decode_token, get_current_user, get_optional_user
from app.core.exceptions import AuthenticationError


class TestCreateToken:
    def test_creates_valid_jwt(self):
        token = create_token(user_id=1, openid="test_openid")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_user_id(self):
        token = create_token(user_id=42, openid="test_openid")
        payload = decode_token(token)
        assert payload["user_id"] == 42
        assert payload["openid"] == "test_openid"

    def test_token_has_expiration(self):
        token = create_token(user_id=1, openid="test_openid")
        payload = decode_token(token)
        assert "exp" in payload


class TestDecodeToken:
    def test_decode_valid_token(self):
        token = create_token(user_id=1, openid="abc")
        payload = decode_token(token)
        assert payload["user_id"] == 1

    def test_decode_expired_token(self):
        from app.core.config import get_settings
        settings = get_settings()
        expired_payload = {
            "user_id": 1,
            "openid": "abc",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        token = jwt.encode(expired_payload, settings.jwt_secret, algorithm="HS256")
        with pytest.raises(AuthenticationError, match="过期"):
            decode_token(token)

    def test_decode_invalid_token(self):
        with pytest.raises(AuthenticationError, match="无效"):
            decode_token("not.a.valid.token")

    def test_decode_tampered_token(self):
        token = create_token(user_id=1, openid="abc")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(AuthenticationError):
            decode_token(tampered)


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_returns_user_id_with_valid_token(self):
        token = create_token(user_id=99, openid="test")
        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {token}"}
        user_id = await get_current_user(request)
        assert user_id == 99

    @pytest.mark.asyncio
    async def test_raises_without_token(self):
        request = MagicMock()
        request.headers = {}
        with pytest.raises(AuthenticationError):
            await get_current_user(request)

    @pytest.mark.asyncio
    async def test_raises_with_invalid_token(self):
        request = MagicMock()
        request.headers = {"Authorization": "Bearer invalid_token"}
        with pytest.raises(AuthenticationError):
            await get_current_user(request)


class TestGetOptionalUser:
    @pytest.mark.asyncio
    async def test_returns_user_id_with_valid_token(self):
        token = create_token(user_id=77, openid="test")
        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {token}"}
        user_id = await get_optional_user(request)
        assert user_id == 77

    @pytest.mark.asyncio
    async def test_returns_none_without_token(self):
        request = MagicMock()
        request.headers = {}
        user_id = await get_optional_user(request)
        assert user_id is None

    @pytest.mark.asyncio
    async def test_returns_none_with_invalid_token(self):
        request = MagicMock()
        request.headers = {"Authorization": "Bearer bad_token"}
        user_id = await get_optional_user(request)
        assert user_id is None
