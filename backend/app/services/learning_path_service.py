"""Owned, immutable confirmed plans; reading checks never become mastery observations."""
import hashlib
import re
import uuid
from datetime import timezone

from fastapi import HTTPException

from app.learning import path_planner
from app.repositories.rag_index_repository import transaction
from app.services.learning_state_service import decoded, encoded, iso, local_day, utcnow


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


async def settings(cur, user_id):
    await cur.execute('SELECT version,edges_json FROM learning_path_settings WHERE user_id=%s', (user_id,))
    row = await cur.fetchone()
    return {'version': row['version'], 'edges': decoded(row['edges_json'])} if row else {'version': 0, 'edges': []}


async def snapshot(cur, user_id, path):
    fields = 'concept_id,label,mastery,attempts,mapping_confidence'
    await cur.execute(f'SELECT {fields} FROM learning_concepts WHERE user_id=%s ORDER BY mastery,concept_id LIMIT 101', (user_id,))
    rows = list(await cur.fetchall())
    pinned = sorted({key for edge in path['edges'] for key in edge})
    if pinned:
        await cur.execute(f'SELECT {fields} FROM learning_concepts WHERE user_id=%s AND concept_id IN (' + ','.join(['%s'] * len(pinned)) + ')', (user_id, *pinned))
        selected = {row['concept_id']: row for row in await cur.fetchall()}
    else:
        selected = {}
    for row in rows:
        if len(selected) < 100:
            selected.setdefault(row['concept_id'], row)
    nodes = sorted(selected.values(), key=lambda row: row['concept_id'])
    if not nodes:
        return nodes, [], len(rows) > 100
    await cur.execute('SELECT c.card_id,c.concept_id,c.quiz_id,c.question_id,c.version,c.due_at FROM learning_cards c '
                      'JOIN quiz_sessions q ON c.quiz_id=q.quiz_id AND c.user_id=q.user_id '
                      'WHERE c.user_id=%s AND c.concept_id IN (' + ','.join(['%s'] * len(nodes)) + ') ORDER BY c.due_at,c.card_id LIMIT 501',
                      (user_id, *[node['concept_id'] for node in nodes]))
    cards = list(await cur.fetchall())
    for card in cards:
        card['due_at'] = card['due_at'].replace(tzinfo=timezone.utc)
    return nodes, cards[:500], len(rows) > 100 or len(cards) > 500


async def get_path(user_id):
    async with transaction() as cur:
        path = await settings(cur, user_id)
        nodes, _, truncated = await snapshot(cur, user_id, path)
    return {**path, 'concepts': nodes, 'truncated': truncated, 'source': 'user_confirmed_prerequisites'}


async def update_path(user_id, request):
    async with transaction() as cur:
        await cur.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (user_id,))
        current = await settings(cur, user_id)
        if current['version'] != request.version:
            raise HTTPException(409, '另一设备已修改学习关系，请刷新后继续')
        wanted = {'edges': sorted([list(edge) for edge in request.edges])}
        if len({key for edge in wanted['edges'] for key in edge}) > 100:
            raise HTTPException(422, '最多关联 100 个知识点')
        nodes, _, _ = await snapshot(cur, user_id, wanted)
        try:
            path_planner.graph([node['concept_id'] for node in nodes], wanted['edges'])
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        if wanted['edges'] == current['edges']:
            return current
        version = current['version'] + 1
        await cur.execute('INSERT INTO learning_path_settings(user_id,version,edges_json,updated_at) VALUES(%s,%s,%s,UTC_TIMESTAMP(6)) '
                          'ON DUPLICATE KEY UPDATE version=VALUES(version),edges_json=VALUES(edges_json),updated_at=VALUES(updated_at)',
                          (user_id, version, encoded(wanted['edges'])))
        return {**wanted, 'version': version}


async def proposal(cur, user_id, minutes, zone):
    if not 5 <= minutes <= 60:
        raise HTTPException(422, '本轮时长应在 5 至 60 分钟之间')
    now = utcnow()
    start, _ = local_day(now, zone)
    path = await settings(cur, user_id)
    nodes, cards, truncated = await snapshot(cur, user_id, path)
    result = path_planner.recommend(nodes, cards, path['edges'], minutes, now)
    result.update(concepts=nodes, path_version=path['version'], edges=path['edges'], day=start.date().isoformat(),
                  timezone=zone, truncated=truncated)
    basis = {'result': result, 'cards': [{**card, 'due_at': card['due_at'].isoformat()} for card in cards]}
    return {**result, 'fingerprint': digest(basis), 'as_of': now.isoformat()}


async def preview(user_id, minutes=15, zone='Asia/Shanghai'):
    async with transaction() as cur:
        return await proposal(cur, user_id, minutes, zone)


async def confirm(user_id, request, key):
    if not key or not re.fullmatch(r'[a-zA-Z0-9:_-]{8,100}', key):
        raise HTTPException(422, '计划确认标识无效')
    request_hash = digest(request.model_dump())
    async with transaction() as cur:
        await cur.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (user_id,))
        await cur.execute('SELECT plan_id,request_hash FROM learning_plans WHERE user_id=%s AND creation_key=%s', (user_id, key))
        old = await cur.fetchone()
        if old:
            if old['request_hash'] != request_hash:
                raise HTTPException(409, '此确认标识已用于其他计划')
            return {'plan_id': old['plan_id'], 'replayed': True}
        fresh = await proposal(cur, user_id, request.minutes, request.timezone)
        if request.fingerprint != fresh['fingerprint']:
            raise HTTPException(409, '学习记录、关系或日期已变化，请重新预览计划')
        if not fresh['items']:
            raise HTTPException(422, '暂无可确认的学习任务')
        await cur.execute('SELECT COUNT(*) AS n FROM learning_plans WHERE user_id=%s AND created_at>=UTC_DATE()', (user_id,))
        if (await cur.fetchone())['n'] >= 20:
            raise HTTPException(429, '今日已确认 20 次计划，请继续已有计划')
        plan_id = 'plan_' + uuid.uuid4().hex
        await cur.execute('INSERT INTO learning_plans(plan_id,user_id,creation_key,request_hash,plan_json,created_at) VALUES(%s,%s,%s,%s,%s,UTC_TIMESTAMP(6))',
                          (plan_id, user_id, key, request_hash, encoded(fresh)))
        return {'plan_id': plan_id, 'replayed': False}


async def owned(cur, plan_id, user_id):
    await cur.execute('SELECT plan_json,created_at FROM learning_plans WHERE plan_id=%s AND user_id=%s', (plan_id, user_id))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(404, '学习计划不存在')
    return {**decoded(row['plan_json']), 'plan_id': plan_id, 'created_at': iso(row['created_at'])}


async def detail(plan_id, user_id):
    async with transaction() as cur:
        plan = await owned(cur, plan_id, user_id)
        path = await settings(cur, user_id)
        await cur.execute('SELECT item_id FROM learning_plan_checks WHERE plan_id=%s AND user_id=%s', (plan_id, user_id))
        checked = {row['item_id'] for row in await cur.fetchall()}
        for item in plan['items']:
            await cur.execute("SELECT version FROM learning_events WHERE user_id=%s AND card_id=%s AND source='review' AND version>=%s LIMIT 1",
                              (user_id, item['card_id'], item['card_version']))
            reviewed = bool(await cur.fetchone())
            item['completion_source'] = ('server_review_event' if reviewed else 'user_read_confirmation' if item['kind'] == 'read' and item['id'] in checked else None)
            item['completed'] = item['completion_source'] is not None
        plan['path_changed'] = path['version'] != plan['path_version']
        start, _ = local_day(utcnow(), plan['timezone'])
        plan['previous_day'] = start.date().isoformat() != plan['day']
        return plan


async def list_plans(user_id):
    async with transaction() as cur:
        await cur.execute('SELECT plan_id,plan_json,created_at FROM learning_plans WHERE user_id=%s ORDER BY created_at DESC,plan_id LIMIT 20', (user_id,))
        return [{'plan_id': row['plan_id'], 'day': decoded(row['plan_json'])['day'], 'minutes': decoded(row['plan_json'])['minutes'],
                 'created_at': iso(row['created_at'])} for row in await cur.fetchall()]


async def mark_read(plan_id, user_id, item_id):
    async with transaction() as cur:
        plan = await owned(cur, plan_id, user_id)
        item = next((item for item in plan['items'] if item['id'] == item_id), None)
        if not item:
            raise HTTPException(404, '计划任务不存在')
        if item['kind'] != 'read':
            raise HTTPException(422, '复习任务必须实际提交作答，不能手动勾选完成')
        await cur.execute('INSERT INTO learning_plan_checks(plan_id,user_id,item_id,created_at) VALUES(%s,%s,%s,UTC_TIMESTAMP(6)) '
                          'ON DUPLICATE KEY UPDATE item_id=item_id', (plan_id, user_id, item_id))
