"""Owned conversations and atomic turn publication, with one active turn per session."""
import hashlib
import json
import re
import uuid

from fastapi import HTTPException

from app.repositories import job_repository as jobs
from app.repositories.rag_index_repository import transaction


def decoded(value):
    return json.loads(value) if isinstance(value, str) else value


def public(row):
    config = decoded(row['config_json'])
    return {'session_id': row['session_id'], 'goal': config['goal'], 'mode': config['mode'], 'doc_ids': config['doc_ids'],
            'version': row['version'], 'pending_task_id': row['pending_task_id'], 'card_id': config.get('card_id'),
            'created_at': row['created_at'].isoformat() + 'Z', 'max_turns': 6}


async def owned(cur, session_id, user_id, lock=False):
    await cur.execute('SELECT * FROM tutor_sessions WHERE session_id=%s AND user_id=%s' + (' FOR UPDATE' if lock else ''), (session_id, user_id))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(404, '辅导会话不存在')
    row['config_json'] = decoded(row['config_json'])
    return row


async def get(session_id, user_id):
    async with transaction() as cur:
        return await owned(cur, session_id, user_id)


async def create(user_id, request, config, key):
    if not re.fullmatch(r'[a-zA-Z0-9:_-]{8,100}', key):
        raise HTTPException(422, '会话请求标识无效')
    fingerprint = hashlib.sha256(jobs.encoded(request.model_dump()).encode()).hexdigest()
    async with transaction() as cur:
        await cur.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (user_id,))
        if not await cur.fetchone():
            raise HTTPException(401, '账户不存在')
        await cur.execute('SELECT * FROM tutor_sessions WHERE user_id=%s AND creation_key=%s', (user_id, key))
        old = await cur.fetchone()
        if old:
            if old['fingerprint'] != fingerprint:
                raise HTTPException(409, '会话请求标识已用于其他内容')
            return public(old)
        await cur.execute('SELECT COUNT(*) AS n FROM tutor_sessions WHERE user_id=%s', (user_id,))
        if (await cur.fetchone())['n'] >= 50:
            raise HTTPException(429, '辅导会话已达 50 个，请先删除不再需要的会话')
        session_id = 'tutor_' + uuid.uuid4().hex
        await cur.execute('INSERT INTO tutor_sessions(session_id,user_id,creation_key,fingerprint,config_json,created_at,updated_at) '
                          'VALUES(%s,%s,%s,%s,%s,UTC_TIMESTAMP(),UTC_TIMESTAMP())', (session_id, user_id, key, fingerprint, jobs.encoded(config)))
        return public(await owned(cur, session_id, user_id))


async def list_sessions(user_id):
    async with transaction() as cur:
        await cur.execute('SELECT * FROM tutor_sessions WHERE user_id=%s ORDER BY updated_at DESC,session_id LIMIT 50', (user_id,))
        return [public(row) for row in await cur.fetchall()]


async def turns(session_id, user_id):
    async with transaction() as cur:
        await owned(cur, session_id, user_id)
        await cur.execute('SELECT turn_number,task_id,learner_text,response_json,created_at FROM tutor_turns WHERE session_id=%s AND user_id=%s ORDER BY turn_number', (session_id, user_id))
        return [{'number': row['turn_number'], 'task_id': row['task_id'], 'message': row['learner_text'],
                 'response': decoded(row['response_json']), 'created_at': row['created_at'].isoformat() + 'Z'} for row in await cur.fetchall()]


async def admit(session_id, user_id, request, key):
    async with transaction() as cur:
        await cur.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (user_id,))
        session = await owned(cur, session_id, user_id, lock=True)
        config = session['config_json']
        payload = {'session_id': session_id, 'session_version': request.version, 'query': request.message, 'title': config['goal'][:160],
                   'doc_ids': config['doc_ids'], 'scope': config['scope'], 'mode': 'rerank'}
        task = await jobs.insert(cur, user_id, 'tutor', payload, key)
        if task['replayed']:
            return task
        if session['version'] != request.version or session['version'] >= 6:
            raise HTTPException(409, '辅导进度已变化或本次会话已结束，请刷新查看')
        if session['pending_task_id']:
            await cur.execute('SELECT status FROM learning_jobs WHERE task_id=%s AND user_id=%s', (session['pending_task_id'], user_id))
            previous = await cur.fetchone()
            if previous and previous['status'] not in jobs.TERMINAL:
                raise HTTPException(409, '上一轮辅导尚未完成，请等待或取消')
        await cur.execute('UPDATE tutor_sessions SET pending_task_id=%s,updated_at=UTC_TIMESTAMP() WHERE session_id=%s AND user_id=%s', (task['task_id'], session_id, user_id))
        return task


async def publish(context, response):
    async with transaction() as cur:
        for doc_id, revision, version in sorted(context.payload['scope']):
            await cur.execute('SELECT m.active,m.revision,m.index_version,d.status FROM kb_index_meta m JOIN kb_documents d ON d.doc_id=m.doc_id '
                              'WHERE m.doc_id=%s AND m.user_id=%s AND d.user_id=%s FOR UPDATE', (doc_id, context.user_id, context.user_id))
            meta = await cur.fetchone()
            if not meta or not meta['active'] or meta['revision'] != revision or meta['index_version'] != version or meta['status'] != 'ready':
                raise HTTPException(409, '材料版本已变化，未发布旧辅导内容')
        session = await owned(cur, context.payload['session_id'], context.user_id, lock=True)
        job = await jobs.running(cur, context.task_id, context.lease_token)
        if (job['kind'] != 'tutor' or job['user_id'] != context.user_id or job['payload_json'] != context.payload
                or session['pending_task_id'] != context.task_id or session['version'] != context.payload['session_version']):
            raise jobs.TaskLeaseLost()
        turn = session['version'] + 1
        await cur.execute('INSERT INTO tutor_turns(session_id,user_id,turn_number,task_id,learner_text,response_json,created_at) VALUES(%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP())',
                          (session['session_id'], context.user_id, turn, context.task_id, context.payload['query'], jobs.encoded(response)))
        await cur.execute('UPDATE tutor_sessions SET version=%s,pending_task_id=NULL,updated_at=UTC_TIMESTAMP() WHERE session_id=%s AND user_id=%s', (turn, session['session_id'], context.user_id))
        reference = {'session_id': session['session_id'], 'turn': turn}
        await jobs.publish_result(cur, job, reference)
        return reference


async def delete(session_id, user_id):
    async with transaction() as cur:
        session = await owned(cur, session_id, user_id, lock=True)
        if session['pending_task_id']:
            await cur.execute('SELECT status FROM learning_jobs WHERE task_id=%s AND user_id=%s', (session['pending_task_id'], user_id))
            job = await cur.fetchone()
            if job and job['status'] not in jobs.TERMINAL:
                raise HTTPException(409, '请先取消正在进行的辅导任务')
        await cur.execute('DELETE FROM tutor_sessions WHERE session_id=%s AND user_id=%s', (session_id, user_id))
