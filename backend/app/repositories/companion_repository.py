"""One persistent thread per authenticated user and character; deletion fences paid work."""
import json
import uuid
from fastapi import HTTPException

from app.companions.catalog import character, story, story_progress, VERSION
from app.repositories import job_repository as jobs
from app.repositories.rag_index_repository import transaction


def decode(value):
    return json.loads(value) if isinstance(value, str) else value


async def lock_user(cur, user_id):
    await cur.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (user_id,))
    if not await cur.fetchone():
        raise HTTPException(401, '账户不存在')


async def owned(cur, user_id, identity, create=False):
    character(identity)
    if create:
        await lock_user(cur, user_id)
        await cur.execute('INSERT INTO companion_threads(user_id,character_id,epoch,memories_json,updated_at) '
                          'VALUES(%s,%s,%s,%s,UTC_TIMESTAMP()) ON DUPLICATE KEY UPDATE user_id=user_id',
                          (user_id, identity, uuid.uuid4().hex, '[]'))
    await cur.execute('SELECT * FROM companion_threads WHERE user_id=%s AND character_id=%s FOR UPDATE', (user_id, identity))
    row = await cur.fetchone()
    if row:
        row['memories_json'] = decode(row['memories_json'])
    return row


async def detail(user_id, identity):
    person = character(identity)
    async with transaction() as cur:
        row = await owned(cur, user_id, identity)
        if not row:
            return dict(character=person, character_id=identity, version=0, turn_count=0, memories=[], turns=[],
                        pending_task_id=None, story=story(identity, 0), chapters=story_progress(identity, 0), canon_version=VERSION)
        await cur.execute('SELECT sequence_number,task_id,learner_text,response_json,created_at FROM companion_turns '
                          'WHERE user_id=%s AND character_id=%s ORDER BY sequence_number DESC LIMIT 100', (user_id, identity))
        turns = [{'number': item['sequence_number'], 'task_id': item['task_id'], 'message': item['learner_text'],
                  'response': decode(item['response_json']), 'created_at': item['created_at'].isoformat() + 'Z'}
                 for item in reversed(await cur.fetchall())]
        return dict(character=person, character_id=identity, version=row['version'], turn_count=row['turn_count'],
                    memories=row['memories_json'], turns=turns, pending_task_id=row['pending_task_id'],
                    story=story(identity, row['turn_count']), chapters=story_progress(identity, row['turn_count']), canon_version=VERSION)


async def check_pending(cur, row):
    if row['pending_task_id']:
        await cur.execute('SELECT status FROM learning_jobs WHERE task_id=%s AND user_id=%s', (row['pending_task_id'], row['user_id']))
        job = await cur.fetchone()
        if job and job['status'] not in jobs.TERMINAL:
            raise HTTPException(409, '伙伴正在回应，请等待或取消后再操作')


async def set_memories(user_id, identity, request):
    async with transaction() as cur:
        row = await owned(cur, user_id, identity, create=True)
        if row['version'] != request.version:
            raise HTTPException(409, '伙伴记忆已变化，请刷新后重试')
        await check_pending(cur, row)
        await cur.execute('UPDATE companion_threads SET memories_json=%s,version=version+1,updated_at=UTC_TIMESTAMP() '
                          'WHERE user_id=%s AND character_id=%s', (jobs.encoded([item.model_dump() for item in request.items]), user_id, identity))
    return await detail(user_id, identity)


async def admit(user_id, identity, request, key):
    async with transaction() as cur:
        row = await owned(cur, user_id, identity, create=True)
        payload = dict(character_id=identity, epoch=row['epoch'], version=request.version, query=request.message,
                       title=character(identity)['name'] + '的对话', scope=[], doc_ids=[])
        task = await jobs.insert(cur, user_id, 'companion', payload, key)
        if task['replayed']:
            return task
        if row['version'] != request.version:
            raise HTTPException(409, '对话进度已变化，请刷新查看')
        await check_pending(cur, row)
        await cur.execute('UPDATE companion_threads SET pending_task_id=%s,updated_at=UTC_TIMESTAMP() WHERE user_id=%s AND character_id=%s',
                          (task['task_id'], user_id, identity))
        return task


async def material(context):
    async with transaction() as cur:
        row = await owned(cur, context.user_id, context.payload['character_id'])
        if not row or row['epoch'] != context.payload['epoch'] or row['version'] != context.payload['version'] or row['pending_task_id'] != context.task_id:
            raise jobs.TaskLeaseLost()
        await jobs.running(cur, context.task_id, context.lease_token)
        await cur.execute('SELECT learner_text,response_json FROM companion_turns WHERE user_id=%s AND character_id=%s '
                          'ORDER BY sequence_number DESC LIMIT 6', (context.user_id, row['character_id']))
        history = [{'learner': item['learner_text'][:500], 'companion': decode(item['response_json'])['dialogue'][:600]}
                   for item in reversed(await cur.fetchall())]
        return dict(character=character(row['character_id']), story=story(row['character_id'], row['turn_count']),
                    memories=row['memories_json'], history=history, message=context.payload['query'], canon_version=VERSION)


async def publish(context, response):
    identity = context.payload['character_id']
    async with transaction() as cur:
        await lock_user(cur, context.user_id)
        row = await owned(cur, context.user_id, identity)
        job = await jobs.running(cur, context.task_id, context.lease_token)
        if (not row or row['epoch'] != context.payload['epoch'] or row['version'] != context.payload['version']
                or row['pending_task_id'] != context.task_id or job['kind'] != 'companion'
                or job['user_id'] != context.user_id or job['payload_json'] != context.payload):
            raise jobs.TaskLeaseLost()
        number = row['turn_count'] + 1
        await cur.execute('INSERT INTO companion_turns(user_id,character_id,sequence_number,task_id,learner_text,response_json,created_at) '
                          'VALUES(%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP())',
                          (context.user_id, identity, number, context.task_id, context.payload['query'], jobs.encoded(response)))
        await cur.execute('DELETE FROM companion_turns WHERE user_id=%s AND character_id=%s AND sequence_number<=%s', (context.user_id, identity, number - 100))
        await cur.execute('UPDATE companion_threads SET version=version+1,turn_count=%s,pending_task_id=NULL,updated_at=UTC_TIMESTAMP() '
                          'WHERE user_id=%s AND character_id=%s', (number, context.user_id, identity))
        result = {'character_id': identity, 'turn': number}
        await jobs.publish_result(cur, job, result)
        return result


async def reset(user_id, identity, request):
    async with transaction() as cur:
        row = await owned(cur, user_id, identity, create=True)
        if row['version'] != request.version:
            raise HTTPException(409, '对话进度已变化，请刷新后重试')
        # Scrub all copies, including failed job input/checkpoints. Retain call counters for budget accounting.
        await cur.execute("UPDATE learning_jobs SET status=CASE WHEN status IN ('queued','running','staging') THEN 'cancelled' ELSE status END,"
                          "stage=CASE WHEN status IN ('queued','running','staging','cancelled') THEN 'cancelled' ELSE stage END,active_fingerprint=NULL,"
                          "payload_json=%s,state_json=%s,result_json=NULL,updated_at=UTC_TIMESTAMP() WHERE user_id=%s AND kind='companion' "
                          "AND JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.character_id'))=%s",
                          (jobs.encoded({'character_id': identity, 'title': '已清除的伙伴对话'}), '{}', user_id, identity))
        memories = [] if request.mode in ('all', 'memory') else row['memories_json']
        # Clearing memory also clears recent context: forgotten facts cannot return through history.
        await cur.execute('DELETE FROM companion_turns WHERE user_id=%s AND character_id=%s', (user_id, identity))
        await cur.execute('UPDATE companion_threads SET epoch=%s,version=version+1,turn_count=%s,memories_json=%s,pending_task_id=NULL,updated_at=UTC_TIMESTAMP() '
                          'WHERE user_id=%s AND character_id=%s',
                          (uuid.uuid4().hex, 0 if request.mode == 'all' else row['turn_count'], jobs.encoded(memories), user_id, identity))
    return await detail(user_id, identity)
