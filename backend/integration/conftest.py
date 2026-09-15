"""Shared fixtures are deliberately restricted to the isolated loopback schema."""
import os
import uuid

import pytest_asyncio

from app.core.config import get_settings
from app.core.db import connect_mysql, close_mysql_pool, get_mysql_pool
from app.repositories.rag_index_repository import transaction


@pytest_asyncio.fixture
async def users():
    settings = get_settings()
    assert os.getenv('AI_LEARN_ENV_FILE') == ''
    assert (settings.mysql_host, settings.mysql_port, settings.mysql_database) == ('127.0.0.1', 23308, 'ai_learn_test')
    await connect_mysql()
    ids = []
    runner = await get_mysql_pool().acquire()
    async with runner.cursor() as lock:
        await lock.execute("SELECT GET_LOCK('ai_learn_test_fixture', 5)")
        assert (await lock.fetchone())[0] == 1
    async with transaction() as cur:
        await cur.execute('SELECT UTC_DATE() AS day')
        day = (await cur.fetchone())['day']
        await cur.execute('SELECT calls,input_bytes FROM provider_call_budget WHERE budget_day=%s', (day,))
        previous_budget = await cur.fetchone()
        await cur.execute('INSERT INTO provider_call_budget(budget_day) VALUES(%s) ON DUPLICATE KEY UPDATE calls=0,input_bytes=0', (day,))
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
            if previous_budget:
                await cur.execute('UPDATE provider_call_budget SET calls=%s,input_bytes=%s WHERE budget_day=%s',
                                  (previous_budget['calls'], previous_budget['input_bytes'], day))
            else:
                await cur.execute('DELETE FROM provider_call_budget WHERE budget_day=%s', (day,))
        async with runner.cursor() as lock:
            await lock.execute("SELECT RELEASE_LOCK('ai_learn_test_fixture')")
        get_mysql_pool().release(runner)
        await close_mysql_pool()
