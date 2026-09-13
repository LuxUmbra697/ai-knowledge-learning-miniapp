"""Shared fixtures are deliberately restricted to the isolated loopback schema."""
import os
import uuid

import pytest_asyncio

from app.core.config import get_settings
from app.core.db import connect_mysql, close_mysql_pool
from app.repositories.rag_index_repository import transaction


@pytest_asyncio.fixture
async def users():
    settings = get_settings()
    assert os.getenv('AI_LEARN_ENV_FILE') == ''
    assert (settings.mysql_host, settings.mysql_port, settings.mysql_database) == ('127.0.0.1', 23308, 'ai_learn_test')
    await connect_mysql()
    ids = []
    try:
        async with transaction() as cur:
            for _ in range(2):
                await cur.execute('INSERT INTO users(openid,nickname) VALUES(%s,%s)', ('test_'+uuid.uuid4().hex, 'Synthetic transaction test'))
                ids.append(cur.lastrowid)
        yield ids
    finally:
        async with transaction() as cur:
            for user_id in ids:
                await cur.execute('DELETE FROM users WHERE id=%s', (user_id,))
        await close_mysql_pool()
