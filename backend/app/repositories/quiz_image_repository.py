"""Owned illustration assets, pre-call daily reservations and fenced publication."""
import uuid

from fastapi import HTTPException

from app.core.config import get_settings
from app.repositories import job_repository as jobs
from app.repositories.rag_index_repository import transaction


async def attach(cur, context, quiz_id, questions):
    from app.services.private_cos_service import object_key
    assets = [('asset_' + uuid.uuid4().hex, question) for question in questions[:2]]
    payload = {'quiz_id': quiz_id, 'title': '练习示意图', 'doc_ids': context.payload['doc_ids'], 'scope': context.payload['scope'],
                   'asset_ids': [asset_id for asset_id, _ in assets]}
    task = await jobs.insert(cur, context.user_id, 'image', payload, 'image_' + context.task_id)
    scope = context.payload['scope'][0] if context.payload['scope'] else None
    for asset_id, question in assets:
        await cur.execute('INSERT INTO quiz_image_assets(asset_id,user_id,quiz_id,question_id,task_id,object_key,doc_id,doc_revision,created_at,updated_at) '
                          'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(),UTC_TIMESTAMP())',
                          (asset_id, context.user_id, quiz_id, question.id, task['task_id'], object_key(asset_id), scope[0] if scope else None, scope[1] if scope else None))
        question.image_asset_id = asset_id
    return task['task_id']


async def for_task(context):
    async with transaction() as cur:
        row = await jobs.running(cur, context.task_id, context.lease_token)
        if row['kind'] != 'image' or row['user_id'] != context.user_id or row['payload_json'] != context.payload:
            raise jobs.TaskLeaseLost()
        await cur.execute('SELECT * FROM quiz_image_assets WHERE task_id=%s AND user_id=%s ORDER BY question_id', (context.task_id, context.user_id))
        result = await cur.fetchall()
        if {row['asset_id'] for row in result} != set(context.payload['asset_ids']) or not 1 <= len(result) <= 2:
            raise HTTPException(409, '配图任务记录不完整')
        return result


async def reserve(context, asset_id):
    async with transaction() as cur:
        await cur.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (context.user_id,))
        if not await cur.fetchone():
            raise jobs.TaskLeaseLost()
        await jobs.running(cur, context.task_id, context.lease_token)
        await cur.execute('SELECT * FROM quiz_image_assets WHERE asset_id=%s AND user_id=%s AND task_id=%s FOR UPDATE', (asset_id, context.user_id, context.task_id))
        asset = await cur.fetchone()
        if not asset:
            raise HTTPException(404, '配图不存在')
        if asset['reserved_day'] is None:
            await cur.execute('SELECT COUNT(*) AS n FROM quiz_image_assets WHERE user_id=%s AND reserved_day=UTC_DATE()', (context.user_id,))
            if (await cur.fetchone())['n'] >= get_settings().image_gen_daily_limit:
                raise HTTPException(429, '今日配图调用额度已用完，文字练习仍可继续')
            await cur.execute("UPDATE quiz_image_assets SET state='reserved',reserved_day=UTC_DATE(),updated_at=UTC_TIMESTAMP() WHERE asset_id=%s", (asset_id,))
        return asset


async def finish(context, outcomes):
    async with transaction() as cur:
        # Match indexing and quiz publication lock order: source versions before the job.
        for doc_id, revision, version in sorted(context.payload['scope']):
            await cur.execute('SELECT m.active,m.revision,m.index_version,d.status FROM kb_index_meta m '
                              'JOIN kb_documents d ON d.doc_id=m.doc_id WHERE m.doc_id=%s AND m.user_id=%s AND d.user_id=%s FOR UPDATE',
                              (doc_id, context.user_id, context.user_id))
            meta = await cur.fetchone()
            if (not meta or not meta['active'] or meta['revision'] != revision or meta['index_version'] != version or meta['status'] != 'ready'):
                raise HTTPException(409, '材料版本已变化，未发布旧配图')
        row = await jobs.running(cur, context.task_id, context.lease_token)
        if row['kind'] != 'image' or row['user_id'] != context.user_id or row['payload_json'] != context.payload:
            raise jobs.TaskLeaseLost()
        if {item['asset_id'] for item in outcomes} != set(context.payload['asset_ids']):
            raise HTTPException(409, '配图结果不完整')
        for item in outcomes:
            await cur.execute('UPDATE quiz_image_assets SET state=%s,metadata_json=%s,error_code=%s,updated_at=UTC_TIMESTAMP() '
                              'WHERE asset_id=%s AND user_id=%s AND task_id=%s',
                              (item['state'], jobs.encoded(item), item.get('error_code'), item['asset_id'], context.user_id, context.task_id))
            if cur.rowcount != 1:
                raise jobs.TaskLeaseLost()
        count = sum(item['state'] == 'ready' for item in outcomes)
        result = {'quiz_id': context.payload['quiz_id'], 'image_count': count,
                  'notice': f'已完成 {count}/{len(outcomes)} 张示意图；配图仅作辅助，不作为答案证据。'}
        await jobs.publish_result(cur, row, result)
        return result


async def get_owned(asset_id, user_id):
    async with transaction() as cur:
        await cur.execute('SELECT a.*,j.status AS job_status,j.stage AS job_stage,j.error_message,j.payload_json, '
                          'EXISTS(SELECT 1 FROM quiz_question_attempts t WHERE t.quiz_id=a.quiz_id AND t.user_id=a.user_id AND t.question_id=a.question_id) AS answered '
                          'FROM quiz_image_assets a JOIN quiz_sessions q ON q.quiz_id=a.quiz_id AND q.user_id=a.user_id '
                          'JOIN learning_jobs j ON j.task_id=a.task_id AND j.user_id=a.user_id WHERE a.asset_id=%s AND a.user_id=%s', (asset_id, user_id))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, '配图不存在')
        if row['doc_id']:
            await cur.execute('SELECT active,revision FROM kb_index_meta WHERE doc_id=%s AND user_id=%s', (row['doc_id'], user_id))
            source = await cur.fetchone()
            if not source or not source['active'] or source['revision'] != row['doc_revision']:
                raise HTTPException(404, '配图来源已变更或删除')
        return row


async def cleanup_candidates():
    async with transaction() as cur:
        await cur.execute("SELECT a.asset_id,a.object_key FROM quiz_image_assets a JOIN learning_jobs j ON j.task_id=a.task_id "
                          'LEFT JOIN kb_index_meta m ON m.doc_id=a.doc_id AND m.user_id=a.user_id '
                          "WHERE a.state<>'removed' AND a.updated_at<UTC_TIMESTAMP()-INTERVAL 10 MINUTE "
                          "AND COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(a.metadata_json,'$.cleanup_attempts')) AS UNSIGNED),0)<5 AND "
                          "(j.status IN ('failed','cancelled') OR a.state='failed' OR "
                          '(a.doc_id IS NOT NULL AND (m.doc_id IS NULL OR m.active=0 OR m.revision<>a.doc_revision))) '
                          'ORDER BY a.updated_at LIMIT 4')
        return await cur.fetchall()


async def removed(asset_id):
    async with transaction() as cur:
        await cur.execute("UPDATE quiz_image_assets SET state='removed',updated_at=UTC_TIMESTAMP() WHERE asset_id=%s", (asset_id,))


async def cleanup_failed(asset_id):
    async with transaction() as cur:
        await cur.execute("UPDATE quiz_image_assets SET metadata_json=JSON_SET(COALESCE(metadata_json,JSON_OBJECT()),'$.cleanup_attempts',"
                          "COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(metadata_json,'$.cleanup_attempts')) AS UNSIGNED),0)+1),"
                          'updated_at=UTC_TIMESTAMP() WHERE asset_id=%s', (asset_id,))
