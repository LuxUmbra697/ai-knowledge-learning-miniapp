"""Small MySQL queue with owned idempotency, fenced leases and persisted call budgets."""
import hashlib
import json
import re
import uuid

from fastapi import HTTPException

from app.repositories.rag_index_repository import transaction
from app.core.config import get_settings

KINDS = {'index', 'answer', 'retrieve', 'quiz', 'report', 'cleanup', 'grade', 'image', 'tutor'}
TERMINAL = {'completed', 'failed', 'cancelled'}
LEASE_SECONDS = 40
MAX_RUNTIME_SECONDS = 180


class TaskLeaseLost(Exception):
    pass


class TaskBudgetExceeded(Exception):
    pass


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def decode(row):
    if row:
        for field in ('payload_json', 'state_json', 'trace_json', 'result_json'):
            if isinstance(row.get(field), str):
                row[field] = json.loads(row[field])
    return row


def public(row, replayed=False):
    return dict(task_id=row['task_id'], kind=row['kind'], status=row['status'], stage=row['stage'],
                title=((row.get('payload_json') or {}).get('file_name') or (row.get('payload_json') or {}).get('title') or (row.get('payload_json') or {}).get('query', ''))[:80],
                created_at=row['created_at'].isoformat()+'Z' if row.get('created_at') else None,
                result=row.get('result_json'), trace=row.get('trace_json') or {},
                error_code=row.get('error_code'), error_message=row.get('error_message'),
                resource_id=(row.get('payload_json') or {}).get('session_id') if row['kind'] == 'tutor' else (row.get('payload_json') or {}).get('quiz_id') if row['kind'] in ('report', 'grade', 'image') else None,
                replayed=replayed, config_version=row.get('config_version', 'jobs-v1'))


async def insert(cur, user_id, kind, payload, key, status='queued'):
    """Caller must own a transaction; this can share the document reservation commit."""
    if kind not in KINDS or not re.fullmatch(r'[a-zA-Z0-9:_-]{8,100}', key):
        raise HTTPException(422, '任务类型或请求标识无效')
    payload_text = encoded(payload)
    if len(payload_text.encode()) > 32000:
        raise HTTPException(422, '任务内容超过大小限制')
    fingerprint = hashlib.sha256(payload_text.encode()).hexdigest()
    await cur.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (user_id,))
    if not await cur.fetchone():
        raise HTTPException(401, '账户不存在')
    await cur.execute('SELECT * FROM learning_jobs WHERE user_id=%s AND kind=%s AND idempotency_key=%s', (user_id, kind, key))
    existing = decode(await cur.fetchone())
    if not existing:
        await cur.execute('SELECT j.* FROM learning_job_request_keys k JOIN learning_jobs j ON j.task_id=k.task_id '
                          'AND j.user_id=k.user_id AND j.kind=k.kind WHERE k.user_id=%s AND k.kind=%s AND k.idempotency_key=%s',
                          (user_id, kind, key))
        existing = decode(await cur.fetchone())
    if existing:
        if existing['fingerprint'] != fingerprint:
            raise HTTPException(409, '请求标识已用于不同内容')
        return public(existing, True)
    await cur.execute('SELECT * FROM learning_jobs WHERE user_id=%s AND kind=%s AND active_fingerprint=%s', (user_id, kind, fingerprint))
    active = decode(await cur.fetchone())
    if active:
        await bind_request_key(cur, user_id, kind, key, active['task_id'])
        return public(active, True)
    if kind == 'report':
        # A completed report is immutable; another device must reuse it, not buy it again.
        await cur.execute("SELECT * FROM learning_jobs WHERE user_id=%s AND kind='report' AND fingerprint=%s AND status='completed' ORDER BY created_at DESC LIMIT 1", (user_id, fingerprint))
        completed = decode(await cur.fetchone())
        if completed:
            await bind_request_key(cur, user_id, kind, key, completed['task_id'])
            return public(completed, True)
    await cur.execute("SELECT COUNT(*) AS count FROM learning_jobs WHERE user_id=%s AND status IN ('queued','running','staging')", (user_id,))
    if (await cur.fetchone())['count'] >= 3:
        raise HTTPException(429, '已有三个待处理任务，请等待或取消后再提交')
    await cur.execute('SELECT COUNT(*) AS count FROM learning_jobs WHERE user_id=%s AND created_at>=UTC_DATE()', (user_id,))
    if (await cur.fetchone())['count'] >= 40:
        raise HTTPException(429, '已达到今日任务数量限制')
    task_id = 'job_' + uuid.uuid4().hex
    trace = dict(trace_id=uuid.uuid4().hex, model_calls=0, tokens=0, nodes=[])
    await cur.execute('INSERT INTO learning_jobs(task_id,user_id,kind,idempotency_key,fingerprint,active_fingerprint,status,stage,'
                      'payload_json,state_json,trace_json,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(),UTC_TIMESTAMP())',
                      (task_id, user_id, kind, key, fingerprint, fingerprint, status, status, payload_text, '{}', encoded(trace)))
    return dict(task_id=task_id, kind=kind, status=status, stage=status, result=None, trace=trace,
                replayed=False, error_code=None, error_message=None, config_version='jobs-v1')


async def bind_request_key(cur, user_id, kind, key, task_id):
    # The caller holds the user row lock; preserve keys even when coalescing tasks.
    await cur.execute('SELECT COUNT(*) AS count FROM learning_job_request_keys WHERE task_id=%s', (task_id,))
    if (await cur.fetchone())['count'] >= 64:
        raise HTTPException(429, '同一任务的重复请求标识过多，请从任务记录查看')
    await cur.execute('INSERT INTO learning_job_request_keys(user_id,kind,idempotency_key,task_id) VALUES(%s,%s,%s,%s)',
                      (user_id, kind, key, task_id))


async def enqueue(user_id, kind, payload, key, status='queued'):
    async with transaction() as cur:
        return await insert(cur, user_id, kind, payload, key, status)


async def activate(task_id, user_id):
    async with transaction() as cur:
        await cur.execute("UPDATE learning_jobs SET status='queued',stage='queued',updated_at=UTC_TIMESTAMP() "
                          "WHERE task_id=%s AND user_id=%s AND status='staging'", (task_id, user_id))
        return cur.rowcount == 1


async def get_owned(task_id, user_id):
    async with transaction() as cur:
        await cur.execute('SELECT * FROM learning_jobs WHERE task_id=%s AND user_id=%s', (task_id, user_id))
        row = decode(await cur.fetchone())
        if not row:
            raise HTTPException(404, '任务不存在')
        result = public(row)
    answer_result = result.get('result') or {}
    if result['kind'] in ('answer', 'retrieve') and answer_result.get('evidence'):
        from app.repositories.rag_index_repository import get_chunk
        try:
            for item in result['result']['evidence']:
                await get_chunk(user_id, item['doc_id'], item['chunk_id'], item['revision'])
        except HTTPException:
            result['result'] = {**result['result'], 'status': 'stale_evidence', 'claims': [], 'evidence': []}
    return result


async def list_owned(user_id, limit=30):
    async with transaction() as cur:
        await cur.execute('SELECT * FROM learning_jobs WHERE user_id=%s ORDER BY created_at DESC LIMIT %s', (user_id, min(limit, 100)))
        items = [public(decode(row)) for row in await cur.fetchall()]
        for item in items:
            if item['kind'] in ('answer', 'retrieve'):
                item['result'] = None
        return items


async def cancel(task_id, user_id):
    async with transaction() as cur:
        await cur.execute('SELECT * FROM learning_jobs WHERE task_id=%s AND user_id=%s FOR UPDATE', (task_id, user_id))
        row = decode(await cur.fetchone())
        if not row:
            raise HTTPException(404, '任务不存在')
        if row['status'] not in TERMINAL:
            await cur.execute("UPDATE learning_jobs SET status='cancelled',stage='cancelled',active_fingerprint=NULL,updated_at=UTC_TIMESTAMP() WHERE task_id=%s", (task_id,))
            row.update(status='cancelled', stage='cancelled')
    return await get_owned(task_id, user_id)


async def claim():
    async with transaction() as cur:
        # MySQL 5.7 has no SKIP LOCKED; the claim transaction is deliberately short.
        for _ in range(20):
            await cur.execute("SELECT *,TIMESTAMPDIFF(SECOND,started_at,UTC_TIMESTAMP()) AS elapsed FROM learning_jobs "
                              "WHERE status='queued' OR (status='running' AND lease_until<UTC_TIMESTAMP()) "
                              'ORDER BY created_at,task_id LIMIT 1 FOR UPDATE')
            row = decode(await cur.fetchone())
            if not row:
                return None
            error = None
            if row['state_json'].get('call_pending'):
                error = ('external_outcome_unknown', '服务在外部调用期间中断，结果与费用状态未知，未自动重复调用')
            elif row['claims'] >= 3 or (row['elapsed'] or 0) >= MAX_RUNTIME_SECONDS:
                error = ('execution_budget_exhausted', '任务超过恢复次数或总耗时限制，请重新提交')
            if error:
                await cur.execute("UPDATE learning_jobs SET status='failed',stage='failed',active_fingerprint=NULL,error_code=%s,error_message=%s,updated_at=UTC_TIMESTAMP() WHERE task_id=%s", (*error, row['task_id']))
                continue
            lease = uuid.uuid4().hex
            stage = 'preparing' if row['claims'] == 0 else 'recovering'
            await cur.execute("UPDATE learning_jobs SET status='running',stage=%s,lease_token=%s,lease_until=TIMESTAMPADD(SECOND,%s,UTC_TIMESTAMP()),"
                              'claims=claims+1,started_at=COALESCE(started_at,UTC_TIMESTAMP()),updated_at=UTC_TIMESTAMP() WHERE task_id=%s',
                              (stage, lease, LEASE_SECONDS, row['task_id']))
            return {**row, 'lease_token': lease, 'status': 'running', 'claims': row['claims']+1}
    return None


async def heartbeat(task_id, lease_token):
    async with transaction() as cur:
        await cur.execute("UPDATE learning_jobs SET lease_until=TIMESTAMPADD(SECOND,%s,UTC_TIMESTAMP()),updated_at=UTC_TIMESTAMP() "
                          "WHERE task_id=%s AND lease_token=%s AND status='running' AND lease_until>=UTC_TIMESTAMP() "
                          'AND TIMESTAMPDIFF(SECOND,started_at,UTC_TIMESTAMP())<%s', (LEASE_SECONDS, task_id, lease_token, MAX_RUNTIME_SECONDS))
        return cur.rowcount == 1


async def running(cur, task_id, lease_token):
    await cur.execute("SELECT * FROM learning_jobs WHERE task_id=%s AND lease_token=%s AND status='running' "
                      'AND lease_until>=UTC_TIMESTAMP() AND TIMESTAMPDIFF(SECOND,started_at,UTC_TIMESTAMP())<%s FOR UPDATE',
                      (task_id, lease_token, MAX_RUNTIME_SECONDS))
    row = decode(await cur.fetchone())
    if not row:
        raise TaskLeaseLost()
    return row


async def checkpoint(task_id, lease_token, stage, value, duration_ms=0):
    async with transaction() as cur:
        row = await running(cur, task_id, lease_token)
        state, trace = row['state_json'], row['trace_json']
        state.setdefault('checkpoints', {})[stage] = value
        trace['nodes'] = [*trace['nodes'], {'stage': stage, 'duration_ms': round(duration_ms, 2)}][-40:]
        await cur.execute('UPDATE learning_jobs SET stage=%s,state_json=%s,trace_json=%s,updated_at=UTC_TIMESTAMP() WHERE task_id=%s',
                          (stage, encoded(state), encoded(trace), task_id))


async def reserve_call(task_id, lease_token, stage, input_bytes=0):
    async with transaction() as cur:
        row = await running(cur, task_id, lease_token)
        state, trace = row['state_json'], row['trace_json']
        counts = state.setdefault('attempts', {})
        attempt = counts.get(stage, 0) + 1
        consumed = trace.get('input_bytes', 0) + max(0, int(input_bytes))
        if state.get('call_pending') or attempt > 3 or trace['model_calls'] >= 12 or trace['tokens'] >= 20000 or consumed > 60000:
            raise TaskBudgetExceeded()
        settings = get_settings()
        await cur.execute('INSERT INTO provider_call_budget(budget_day) VALUES(UTC_DATE()) ON DUPLICATE KEY UPDATE budget_day=budget_day')
        await cur.execute('UPDATE provider_call_budget SET calls=calls+1,input_bytes=input_bytes+%s '
                          'WHERE budget_day=UTC_DATE() AND calls<%s AND input_bytes+%s<=%s',
                          (max(0, input_bytes), settings.worker_daily_provider_calls, max(0, input_bytes),
                           settings.worker_daily_provider_input_bytes))
        if cur.rowcount != 1:
            raise TaskBudgetExceeded()
        counts[stage] = attempt
        state['call_pending'] = {'stage': stage, 'attempt': attempt}
        trace['model_calls'] += 1
        trace['input_bytes'] = consumed
        await cur.execute('UPDATE learning_jobs SET stage=%s,state_json=%s,trace_json=%s,updated_at=UTC_TIMESTAMP() WHERE task_id=%s',
                          (stage, encoded(state), encoded(trace), task_id))
        return attempt


async def complete_call(task_id, lease_token, stage, output, tokens):
    async with transaction() as cur:
        row = await running(cur, task_id, lease_token)
        state, trace = row['state_json'], row['trace_json']
        if (state.get('call_pending') or {}).get('stage') != stage:
            raise TaskLeaseLost()
        state['call_pending'] = None
        state.setdefault('checkpoints', {})[stage] = output
        if tokens is None:
            trace['unmetered_calls'] = trace.get('unmetered_calls', 0) + 1
        else:
            trace['tokens'] += max(0, int(tokens))
        await cur.execute('UPDATE learning_jobs SET state_json=%s,trace_json=%s,updated_at=UTC_TIMESTAMP() WHERE task_id=%s',
                          (encoded(state), encoded(trace), task_id))


async def finish(task_id, lease_token, result, error_code=None, error_message=None):
    async with transaction() as cur:
        try:
            row = await running(cur, task_id, lease_token)
        except TaskLeaseLost:
            return False
        if row['state_json'].get('call_pending') and not error_code:
            return False
        if row['state_json'].get('call_pending'):
            error_code = 'external_outcome_unknown'
            error_message = '外部调用被中断，结果与费用状态未知，未自动重复调用'
        status = 'failed' if error_code else 'completed'
        await cur.execute('UPDATE learning_jobs SET status=%s,stage=%s,result_json=%s,error_code=%s,error_message=%s,'
                          "active_fingerprint=NULL,lease_token=NULL,lease_until=CASE WHEN status='failed' THEN lease_until ELSE NULL END,updated_at=UTC_TIMESTAMP() WHERE task_id=%s",
                          (status, status, encoded(result) if result is not None else None, error_code, error_message, task_id))
        return True


async def publish_result(cur, row, result):
    """The caller has locked a running job and commits its domain writes in this transaction."""
    if row['state_json'].get('call_pending'):
        raise TaskLeaseLost()
    await cur.execute("UPDATE learning_jobs SET status='completed',stage='completed',result_json=%s,"
                      'active_fingerprint=NULL,lease_token=NULL,lease_until=NULL,updated_at=UTC_TIMESTAMP() WHERE task_id=%s',
                      (encoded(result), row['task_id']))
