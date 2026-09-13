"""Real InnoDB races with unique synthetic users; no external provider calls."""
import asyncio
import hashlib
import os
import uuid

from fastapi import HTTPException
from langchain_core.documents import Document
import pytest
import pytest_asyncio

from app.core.config import get_settings
from app.core.db import connect_mysql, close_mysql_pool
from app.repositories import rag_index_repository as repo, knowledge_repository


@pytest_asyncio.fixture
async def users():
    settings = get_settings()
    assert os.getenv('AI_LEARN_ENV_FILE') == ''
    assert (settings.mysql_host, settings.mysql_port, settings.mysql_database) == ('127.0.0.1', 23308, 'ai_learn_local')
    await connect_mysql()
    ids = []
    try:
        async with repo.transaction() as cur:
            for _ in range(2):
                await cur.execute('INSERT INTO users(openid,nickname) VALUES(%s,%s)', ('test_'+uuid.uuid4().hex, '合成事务测试'))
                ids.append(cur.lastrowid)
        yield ids
    finally:
        async with repo.transaction() as cur:
            for user_id in ids:
                await cur.execute('DELETE FROM users WHERE id=%s', (user_id,))
        await close_mysql_pool()


async def reserve(user, text='材料', quota=10):
    return await repo.reserve('doc_'+uuid.uuid4().hex, user, '合成材料.md', 'md', len(text),
                              hashlib.sha256(text.encode()).hexdigest(), 'v1', quota)


@pytest.mark.asyncio
async def test_concurrent_duplicate_and_quota_are_atomic(users):
    first, second = await asyncio.gather(reserve(users[0]), reserve(users[0]))
    assert first['doc_id'] == second['doc_id']
    assert sorted([first['duplicate'], second['duplicate']]) == [False, True]
    results = await asyncio.gather(reserve(users[1], 'A', 1), reserve(users[1], 'B', 1), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert len(await knowledge_repository.list_documents(users[1])) == 1


@pytest.mark.asyncio
async def test_publish_reindex_tombstone_and_cross_user_scope(users):
    doc = await reserve(users[0])
    doc_id = doc['doc_id']
    chunk = Document(page_content='原文证据', metadata={'chunk_id': 'c1', 'page': 2, 'section': '第一章'})
    assert await repo.publish(doc_id, users[0], 1, 'v1', [chunk])
    rows = await repo.scoped_chunks(users[0], [doc_id], 'v1')
    assert len(rows) == 1 and rows[0]['metadata']['page'] == 2
    for action in (lambda: repo.scoped_chunks(users[1], [doc_id], 'v1'),
                   lambda: repo.get_chunk(users[1], doc_id, 'c1', 1),
                   lambda: repo.tombstone(doc_id, users[1]),
                   lambda: repo.begin_reindex(doc_id, users[1], 'v2')):
        with pytest.raises(HTTPException) as error:
            await action()
        assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        await repo.scoped_chunks(users[0], [doc_id], 'other-embedding')
    assert error.value.status_code == 409
    meta = await repo.begin_reindex(doc_id, users[0], 'v2')
    assert meta['revision'] == 2
    assert not await repo.publish(doc_id, users[0], 1, 'v1', [chunk])
    assert await repo.publish(doc_id, users[0], 2, 'v2', [chunk])
    with pytest.raises(HTTPException):
        await repo.get_chunk(users[0], doc_id, 'c1', 1)
    await repo.tombstone(doc_id, users[0])
    assert not await repo.publish(doc_id, users[0], 2, 'v2', [chunk])
    assert await knowledge_repository.list_documents(users[0]) == []
    with pytest.raises(HTTPException) as error:
        await repo.scoped_chunks(users[0], [doc_id], 'v2')
    assert error.value.status_code == 404
    replacement = await reserve(users[0])
    assert replacement['doc_id'] != doc_id and not replacement['duplicate']
