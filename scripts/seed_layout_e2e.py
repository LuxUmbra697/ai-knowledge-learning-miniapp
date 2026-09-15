"""Text-only layout fixtures. Loopback database and e2e accounts only; no providers."""
import argparse
import asyncio
import hashlib
import json
import uuid

from run_local import configure

configure()

from langchain_core.documents import Document
from app.core.db import connect_mysql, close_mysql_pool
from app.repositories import rag_index_repository as index, job_repository as jobs
from app.services.vector_store_service import index_version


async def main(user_id):
    await connect_mysql()
    try:
        async with index.transaction() as cur:
            await cur.execute('SELECT username FROM account_credentials WHERE user_id=%s', (user_id,))
            row = await cur.fetchone()
            if not row or not row['username'].startswith('e2e_'):
                raise ValueError('Only synthetic e2e accounts may receive layout fixtures')
        title = '学习方法与知识关联：从主动回忆到跨章节复习的完整学习笔记（合成布局验收资料）.md'
        content = '主动回忆需要先用自己的话解释概念，再检查原文证据。复习计划应尊重前置知识与实际作答记录。\n这段材料仅用于合成界面验收，不是学习效果证据。'
        version = index_version()
        doc = await index.reserve('doc_' + uuid.uuid4().hex, user_id, title, 'md', len(content.encode()), hashlib.sha256(content.encode()).hexdigest(), version, 10)
        # Never queue an embedding job. These SQL chunks test rendering, not retrieval quality.
        await jobs.cancel(doc['task_id'], user_id)
        await index.publish(doc['doc_id'], user_id, 1, version, [Document(page_content=content, metadata={
            'chunk_id': 'layout_' + str(i), 'section': '第 ' + str(i + 1) + ' 节：学习方法与知识证据',
            'content_hash': hashlib.sha256(content.encode()).hexdigest(),
        }) for i in range(22)])
        print(json.dumps({'docId': doc['doc_id'], 'taskId': doc['task_id'], 'provider_calls': 0}))
    finally:
        await close_mysql_pool()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--user-id', type=int, required=True)
    asyncio.run(main(parser.parse_args().user_id))
