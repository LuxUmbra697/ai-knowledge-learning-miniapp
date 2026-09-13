"""Owned index revisions and atomic publication. SQL is the retrieval authority."""
from contextlib import asynccontextmanager
import json

from aiomysql import DictCursor
from fastapi import HTTPException

from app.core.db import get_mysql_pool
from app.core.exceptions import KnowledgeBaseError


@asynccontextmanager
async def transaction():
    pool = get_mysql_pool()
    if pool is None:
        raise RuntimeError('Database unavailable')
    async with pool.acquire() as conn:
        await conn.begin()
        try:
            async with conn.cursor(DictCursor) as cur:
                yield cur
            await conn.commit()
        except BaseException:
            await conn.rollback()
            raise


async def reserve(doc_id, user_id, filename, file_type, size, file_hash, version, quota):
    from app.repositories import job_repository as jobs
    async with transaction() as cur:
        # Serialize both quota and duplicate checks across API instances.
        await cur.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (user_id,))
        if not await cur.fetchone():
            raise HTTPException(401, '账户不存在')
        await cur.execute('SELECT d.*, m.revision, m.index_version,m.job_id AS task_id FROM kb_documents d '
                          'JOIN kb_index_meta m ON m.doc_id=d.doc_id '
                          'WHERE m.user_id=%s AND m.file_hash=%s AND m.active=1', (user_id, file_hash))
        existing = await cur.fetchone()
        if existing:
            return {**existing, 'duplicate': True}
        await cur.execute('SELECT COUNT(*) AS count FROM kb_documents d LEFT JOIN kb_index_meta m '
                          'ON m.doc_id=d.doc_id WHERE d.user_id=%s AND (m.active=1 OR m.doc_id IS NULL)', (user_id,))
        if (await cur.fetchone())['count'] >= quota:
            raise KnowledgeBaseError(f'知识库文档数量已达上限（最多 {quota} 篇），请先删除部分文档')
        await cur.execute("INSERT INTO kb_documents(doc_id,user_id,file_name,file_type,file_size,status) "
                          "VALUES(%s,%s,%s,%s,%s,'processing')", (doc_id, user_id, filename, file_type, size))
        job = await jobs.insert(cur, user_id, 'index', {'doc_id': doc_id, 'revision': 1, 'index_version': version,
                               'storage_key': f'{doc_id}.{file_type}', 'file_type': file_type, 'file_name': filename}, f'{doc_id}:1', 'staging')
        await cur.execute('INSERT INTO kb_index_meta(doc_id,user_id,file_hash,index_version,storage_key,job_id) '
                          'VALUES(%s,%s,%s,%s,%s,%s)', (doc_id, user_id, file_hash, version, f'{doc_id}.{file_type}', job['task_id']))
        return dict(doc_id=doc_id, file_name=filename, status='processing', revision=1,
                    index_version=version, duplicate=False, task_id=job['task_id'])


async def is_current(doc_id, user_id, revision, version):
    async with transaction() as cur:
        await cur.execute('SELECT doc_id FROM kb_index_meta WHERE doc_id=%s AND user_id=%s '
                          'AND revision=%s AND index_version=%s AND active=1', (doc_id, user_id, revision, version))
        return bool(await cur.fetchone())


async def publish(doc_id, user_id, revision, version, chunks, context=None):
    async with transaction() as cur:
        await cur.execute('SELECT active,revision,index_version FROM kb_index_meta WHERE doc_id=%s AND user_id=%s '
                          'FOR UPDATE', (doc_id, user_id))
        meta = await cur.fetchone()
        if not meta or not meta['active'] or meta['revision'] != revision or meta['index_version'] != version:
            return False
        if context:
            from app.repositories import job_repository as jobs
            await jobs.running(cur, context.task_id, context.lease_token)
        await cur.execute('DELETE FROM kb_chunks WHERE doc_id=%s AND user_id=%s', (doc_id, user_id))
        await cur.executemany('INSERT INTO kb_chunks(doc_id,chunk_id,user_id,revision,index_version,content,metadata_json) '
                              'VALUES(%s,%s,%s,%s,%s,%s,%s)', [
            (doc_id, chunk.metadata['chunk_id'], user_id, revision, version, chunk.page_content,
             json.dumps(chunk.metadata, ensure_ascii=False)) for chunk in chunks])
        await cur.execute("UPDATE kb_documents SET status='ready',chunk_count=%s,error_message=NULL "
                          'WHERE doc_id=%s AND user_id=%s', (len(chunks), doc_id, user_id))
        if context:
            await cur.execute("UPDATE learning_jobs SET status='completed',stage='completed',active_fingerprint=NULL,result_json=%s,"
                              'lease_token=NULL,lease_until=NULL,updated_at=UTC_TIMESTAMP() WHERE task_id=%s',
                              (json.dumps({'doc_id': doc_id, 'chunk_count': len(chunks), 'revision': revision}), context.task_id))
        return True


async def fail(doc_id, user_id, revision, version, message, context=None):
    async with transaction() as cur:
        if context:
            from app.repositories import job_repository as jobs
            await cur.execute('SELECT doc_id FROM kb_index_meta WHERE doc_id=%s AND user_id=%s FOR UPDATE', (doc_id, user_id))
            await jobs.running(cur, context.task_id, context.lease_token)
        await cur.execute("UPDATE kb_documents d JOIN kb_index_meta m ON d.doc_id=m.doc_id "
                          "SET d.status='failed',d.chunk_count=0,d.error_message=%s "
                          'WHERE d.doc_id=%s AND d.user_id=%s AND m.active=1 AND m.revision=%s AND m.index_version=%s',
                          (message, doc_id, user_id, revision, version))


async def maintenance_rows():
    async with transaction() as cur:
        await cur.execute("UPDATE kb_documents d JOIN kb_index_meta m ON d.doc_id=m.doc_id JOIN learning_jobs j ON m.job_id=j.task_id "
                          "SET d.status='failed',d.error_message=CASE WHEN j.status='cancelled' THEN '索引任务已取消，可重新建立索引' ELSE COALESCE(j.error_message,'索引任务失败，请重新建立索引') END "
                          "WHERE d.status='processing' AND m.active=1 AND j.status IN ('failed','cancelled')")
        await cur.execute('SELECT m.*,d.file_type,j.status AS job_status FROM kb_index_meta m JOIN kb_documents d ON m.doc_id=d.doc_id '
                          'LEFT JOIN learning_jobs j ON m.job_id=j.task_id '
                          "WHERE (m.active=0 AND m.cleanup_pending=1 AND (j.lease_until IS NULL OR j.lease_until<UTC_TIMESTAMP()-INTERVAL 60 SECOND)) "
                          "OR (j.status='staging' AND j.created_at<UTC_TIMESTAMP()-INTERVAL 60 SECOND) LIMIT 5")
        return await cur.fetchall()


async def tombstone(doc_id, user_id):
    async with transaction() as cur:
        await cur.execute('SELECT d.file_type,m.* FROM kb_documents d LEFT JOIN kb_index_meta m ON d.doc_id=m.doc_id '
                          'WHERE d.doc_id=%s AND d.user_id=%s FOR UPDATE', (doc_id, user_id))
        row = await cur.fetchone()
        if not row or row.get('active') == 0:
            raise HTTPException(404, '文档不存在')
        if row.get('doc_id') is None:
            await cur.execute('INSERT INTO kb_index_meta(doc_id,user_id,index_version,storage_key,active,cleanup_pending) '
                              'VALUES(%s,%s,%s,%s,0,1)', (doc_id, user_id, 'legacy', f'{doc_id}.{row["file_type"]}'))
            row.update(revision=1, index_version='legacy', storage_key=f'{doc_id}.{row["file_type"]}')
        else:
            await cur.execute('UPDATE kb_index_meta SET active=0,file_hash=NULL,cleanup_pending=1 '
                              'WHERE doc_id=%s AND user_id=%s', (doc_id, user_id))
        if row.get('job_id'):
            await cur.execute("UPDATE learning_jobs SET status='cancelled',stage='cancelled',active_fingerprint=NULL,updated_at=UTC_TIMESTAMP() "
                              "WHERE task_id=%s AND user_id=%s AND status IN ('staging','queued','running')", (row['job_id'], user_id))
        await cur.execute('DELETE FROM kb_chunks WHERE doc_id=%s AND user_id=%s', (doc_id, user_id))
        return row


async def cleanup_done(doc_id, user_id):
    async with transaction() as cur:
        # A cancelled asyncio task cannot stop an in-flight native Chroma/HTTP thread.
        # Keep the tombstone pending beyond its lease so maintenance sweeps late writes.
        await cur.execute('UPDATE kb_index_meta m LEFT JOIN learning_jobs j ON m.job_id=j.task_id '
                          'SET m.cleanup_pending=0 WHERE m.doc_id=%s AND m.user_id=%s AND m.active=0 '
                          'AND (j.lease_until IS NULL OR j.lease_until<UTC_TIMESTAMP()-INTERVAL 60 SECOND)',
                          (doc_id, user_id))


async def begin_reindex(doc_id, user_id, version):
    from app.repositories import job_repository as jobs
    async with transaction() as cur:
        await cur.execute('SELECT d.status,d.file_type,d.file_name,m.* FROM kb_documents d LEFT JOIN kb_index_meta m ON d.doc_id=m.doc_id '
                          'WHERE d.doc_id=%s AND d.user_id=%s FOR UPDATE', (doc_id, user_id))
        row = await cur.fetchone()
        if not row or row.get('active') == 0:
            raise HTTPException(404, '文档不存在')
        if row['status'] == 'processing':
            raise HTTPException(409, '文档正在处理中，请等待当前任务完成')
        old_revision, old_version = row.get('revision') or 0, row.get('index_version') or 'legacy'
        if row.get('doc_id') is None:
            await cur.execute('INSERT INTO kb_index_meta(doc_id,user_id,index_version,storage_key) VALUES(%s,%s,%s,%s)',
                              (doc_id, user_id, version, f'{doc_id}.{row["file_type"]}'))
        else:
            await cur.execute('UPDATE kb_index_meta SET revision=revision+1,index_version=%s WHERE doc_id=%s AND user_id=%s',
                              (version, doc_id, user_id))
        await cur.execute("UPDATE kb_documents SET status='processing',chunk_count=0,error_message=NULL WHERE doc_id=%s AND user_id=%s",
                          (doc_id, user_id))
        storage_key = row.get('storage_key') or f'{doc_id}.{row["file_type"]}'
        job = await jobs.insert(cur, user_id, 'index', {'doc_id': doc_id, 'revision': old_revision+1, 'index_version': version,
                               'storage_key': storage_key, 'file_type': row['file_type'], 'file_name': row['file_name'], 'previous': [old_revision, old_version]}, f'{doc_id}:{old_revision+1}')
        await cur.execute('UPDATE kb_index_meta SET job_id=%s WHERE doc_id=%s AND user_id=%s', (job['task_id'], doc_id, user_id))
        return dict(revision=old_revision+1, index_version=version, previous=(old_revision, old_version),
                    file_type=row['file_type'], storage_key=storage_key, task_id=job['task_id'])


async def scoped_chunks(user_id, doc_ids, version, limit=10000):
    if not doc_ids or len(doc_ids) > 10:
        raise HTTPException(422, '请选择 1 至 10 篇文档')
    doc_ids = sorted(set(doc_ids))
    marks = ','.join(['%s'] * len(doc_ids))
    async with transaction() as cur:
        await cur.execute('SELECT d.doc_id,d.status,m.active,m.index_version FROM kb_documents d '
                          f'LEFT JOIN kb_index_meta m ON d.doc_id=m.doc_id WHERE d.user_id=%s AND d.doc_id IN ({marks})',
                          (user_id, *doc_ids))
        docs = await cur.fetchall()
        if len(docs) != len(doc_ids) or any(row['active'] == 0 for row in docs):
            raise HTTPException(404, '文档不存在')
        if any(row['index_version'] != version for row in docs):
            raise HTTPException(409, '索引版本已变化，请先重新建立文档索引')
        if any(row['status'] != 'ready' for row in docs):
            raise HTTPException(409, '文档尚未就绪')
        await cur.execute('SELECT c.*,d.file_name FROM kb_chunks c JOIN kb_documents d ON c.doc_id=d.doc_id '
                          'JOIN kb_index_meta m ON c.doc_id=m.doc_id AND c.revision=m.revision '
                          'AND c.index_version=m.index_version '
                          f'WHERE c.user_id=%s AND d.user_id=%s AND m.active=1 AND d.status=\'ready\' AND c.doc_id IN ({marks}) '
                          'ORDER BY c.doc_id,c.chunk_id LIMIT %s', (user_id, user_id, *doc_ids, limit+1))
        rows = await cur.fetchall()
        if len(rows) > limit:
            raise HTTPException(422, '本次材料过多，请减少文档范围')
        return [{**row, 'metadata': json.loads(row['metadata_json'])} for row in rows]


async def get_chunk(user_id, doc_id, chunk_id, revision):
    async with transaction() as cur:
        await cur.execute('SELECT c.*,d.file_name FROM kb_chunks c JOIN kb_documents d ON c.doc_id=d.doc_id '
                          'JOIN kb_index_meta m ON c.doc_id=m.doc_id AND c.revision=m.revision '
                          'WHERE c.user_id=%s AND d.user_id=%s AND c.doc_id=%s AND c.chunk_id=%s AND c.revision=%s '
                          "AND m.active=1 AND d.status='ready'", (user_id, user_id, doc_id, chunk_id, revision))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, '引用已失效或文档不存在')
        return {**row, 'metadata': json.loads(row['metadata_json'])}
