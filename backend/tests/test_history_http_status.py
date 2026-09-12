from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from app.core.auth import create_token
from app.main import app


@pytest.mark.asyncio
async def test_missing_or_unowned_history_uses_http_404():
    with patch('app.services.history_service.get_quiz_detail', new_callable=AsyncMock, return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get('/api/v1/user/quizzes/not-owned', headers={'Authorization': 'Bearer ' + create_token(1, 'test')})
    assert response.status_code == 404
    assert response.json()['data'] is None
