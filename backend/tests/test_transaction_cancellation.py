"""A lost connection during cancellation must not replace the original cancellation signal."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.repositories import rag_index_repository as index


@pytest.mark.asyncio
@pytest.mark.parametrize('closed', [True, False])
async def test_cancelled_transaction_preserves_cancellation_if_rollback_is_unavailable(monkeypatch, closed):
    @asynccontextmanager
    async def cursor(*_args):
        yield object()
    conn = SimpleNamespace(begin=AsyncMock(), commit=AsyncMock(), closed=closed, close=Mock(), cursor=cursor,
                           rollback=AsyncMock(side_effect=RuntimeError('Lost connection during rollback')))
    @asynccontextmanager
    async def acquire():
        yield conn
    monkeypatch.setattr(index, 'get_mysql_pool', lambda: SimpleNamespace(acquire=acquire))
    with pytest.raises(asyncio.CancelledError, match='Original cancellation'):
        async with index.transaction():
            raise asyncio.CancelledError('Original cancellation')
    conn.commit.assert_not_awaited()
    if closed:
        conn.rollback.assert_not_awaited()
    else:
        conn.close.assert_called_once()
