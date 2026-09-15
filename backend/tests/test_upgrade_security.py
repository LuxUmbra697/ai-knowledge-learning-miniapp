"""Regression cases discovered during the M0 audit."""

from unittest.mock import AsyncMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.auth import create_token, decode_token
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.main import app


@pytest.mark.asyncio
async def test_task_requires_authentication():
    with patch("app.services.quiz_service.task_repository.get_task", new_callable=AsyncMock,
               return_value={"task_id": "private", "status": "running", "user_id": 1}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/quiz/task/private")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_task_lookup_is_scoped_to_authenticated_owner():
    with patch("app.services.quiz_service.task_repository.get_task", new_callable=AsyncMock,
               return_value=None) as lookup:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/quiz/task/private", headers={
                "Authorization": "Bearer " + create_token(2, "user2")})
    assert response.status_code == 404
    lookup.assert_awaited_once_with("private", 2)


@pytest.mark.parametrize("payload", [{"user_id": 1}, {"user_id": "1", "exp": 4102444800},
                                    {"user_id": -1, "exp": 4102444800}, {"exp": 4102444800}])
def test_incomplete_or_invalid_jwt_identity_is_rejected(payload):
    token = jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")
    with pytest.raises(AuthenticationError):
        decode_token(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/quiz/generate", "/api/v1/quiz/generate/async", "/api/v1/report/generate"])
async def test_costly_operations_require_authentication(path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, json={})
    assert response.status_code == 401
