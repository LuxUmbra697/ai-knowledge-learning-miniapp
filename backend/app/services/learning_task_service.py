"""Authenticated task admission and compatibility waits; only workers call models."""
import asyncio
import uuid
from time import monotonic

from fastapi import HTTPException

from app.repositories import job_repository as jobs, rag_index_repository as index
from app.services import vector_store_service as vectors


async def create_answer(user_id, request, key=None):
    return await _create_grounded(user_id, request, key, 'answer')


async def create_retrieval(user_id, request, key=None):
    return await _create_grounded(user_id, request, key, 'retrieve')


async def _create_grounded(user_id, request, key, kind):
    doc_ids = sorted(set(request.doc_ids))
    rows = await index.scoped_chunks(user_id, doc_ids, vectors.index_version())
    scope = sorted({(row['doc_id'], row['revision'], row['index_version']) for row in rows})
    return await jobs.enqueue(user_id, kind, dict(query=request.query, doc_ids=doc_ids,
                              mode=request.mode, scope=scope), key or uuid.uuid4().hex)


async def wait_result(task_id, user_id, seconds=55):
    deadline = monotonic() + seconds
    while monotonic() < deadline:
        task = await jobs.get_owned(task_id, user_id)
        if task['status'] == 'completed':
            return task['result']
        if task['status'] in ('failed', 'cancelled'):
            raise HTTPException(409, task.get('error_message') or '任务已取消')
        await asyncio.sleep(.5)
    raise HTTPException(409, '任务仍在处理中，请到任务记录继续查看')
