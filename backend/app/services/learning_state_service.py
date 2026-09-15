"""Transactional learning observations, FSRS reviews and user-confirmed error labels."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.learning import knowledge_tracing as bkt
from app.learning import scheduler
from app.repositories.rag_index_repository import transaction
from app.services.quiz_evidence_service import visible_question


def utcnow():
    return datetime.now(timezone.utc)


def encoded(data):
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'))


def decoded(data):
    return json.loads(data) if isinstance(data, str) else data


def sql_time(value):
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat()


def local_day(now, name):
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, '时区无效，请使用 IANA 时区名称') from None
    start = now.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


class ReviewSubmission(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1, strict=True)
    selected_answers: list[str] = Field(min_length=1, max_length=8)
    duration_ms: int = Field(default=0, ge=0, le=86400000)


class CardSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    favorite: StrictBool | None = None
    diagnosis: Literal['concept_confusion', 'missing_prerequisite', 'careless', 'reasoning_gap'] | None = None


async def observe(cur, user_id, mapping, correct, now):
    await cur.execute('INSERT INTO learning_concepts(user_id,concept_id,label,mapping_confidence,updated_at) VALUES(%s,%s,%s,%s,%s) '
                      'ON DUPLICATE KEY UPDATE label=VALUES(label),mapping_confidence=VALUES(mapping_confidence)',
                      (user_id, mapping['id'], mapping['label'], mapping['confidence'], sql_time(now)))
    await cur.execute('SELECT mastery,attempts FROM learning_concepts WHERE user_id=%s AND concept_id=%s FOR UPDATE', (user_id, mapping['id']))
    before = await cur.fetchone()
    calculation = bkt.update(before['mastery'], correct)
    await cur.execute('UPDATE learning_concepts SET mastery=%s,attempts=attempts+1,correct_count=correct_count+%s,updated_at=%s '
                      'WHERE user_id=%s AND concept_id=%s',
                      (calculation['mastery'], int(correct), sql_time(now), user_id, mapping['id']))
    return {**calculation, 'observation_count': before['attempts'] + 1, 'mapping': mapping}


async def record_initial(cur, user_id, quiz_id, question, record):
    now = utcnow()
    card_id = 'card_' + hashlib.sha256(encoded([user_id, quiz_id, question['id']]).encode()).hexdigest()[:32]
    mapping = bkt.concept_mapping(question, quiz_id)
    knowledge = await observe(cur, user_id, mapping, record['is_correct'], now)
    schedule = scheduler.review(None, card_id, record['is_correct'], now)
    due = datetime.fromisoformat(schedule['card']['due'])
    await cur.execute('INSERT INTO learning_cards(card_id,user_id,quiz_id,question_id,concept_id,card_json,due_at,last_correct,wrong_count,created_at,updated_at) '
                      'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                      (card_id, user_id, quiz_id, question['id'], mapping['id'], encoded(schedule['card']), sql_time(due),
                       record['is_correct'], int(not record['is_correct']), sql_time(now), sql_time(now)))
    event = {'record': record, 'knowledge': knowledge, 'schedule': schedule, 'version': 1, 'due_at': due.isoformat()}
    await cur.execute('INSERT INTO learning_events(user_id,card_id,version,source,event_json,created_at) VALUES(%s,%s,0,\'practice\',%s,%s)',
                      (user_id, card_id, encoded(event), sql_time(now)))


async def summary(user_id, zone_name='Asia/Shanghai'):
    now = utcnow()
    start, end = local_day(now, zone_name)
    beginning = start - timedelta(days=13)
    async with transaction() as cur:
        await cur.execute('SELECT COUNT(*) AS total,COALESCE(SUM(due_at<=%s),0) AS due FROM learning_cards WHERE user_id=%s', (sql_time(now), user_id))
        counts = await cur.fetchone()
        await cur.execute('SELECT source,COUNT(*) AS n FROM learning_events WHERE user_id=%s AND created_at>=%s AND created_at<%s GROUP BY source',
                          (user_id, sql_time(start), sql_time(end)))
        today = {r['source']: int(r['n']) for r in await cur.fetchall()}
        await cur.execute('SELECT concept_id,label,mapping_confidence,mastery,attempts,correct_count FROM learning_concepts WHERE user_id=%s ORDER BY mastery,concept_id LIMIT 100', (user_id,))
        concepts = await cur.fetchall()
        await cur.execute('SELECT created_at FROM learning_events WHERE user_id=%s AND created_at>=%s AND created_at<%s ORDER BY created_at LIMIT 5001',
                          (user_id, sql_time(beginning), sql_time(end)))
        events = await cur.fetchall()
    trend = {(beginning + timedelta(days=i)).date().isoformat(): 0 for i in range(14)}
    for event in events[:5000]:
        day = event['created_at'].replace(tzinfo=timezone.utc).astimezone(start.tzinfo).date().isoformat()
        trend[day] += 1
    return {'as_of': now.isoformat(), 'timezone': zone_name, 'total_cards': int(counts['total']), 'due_count': int(counts['due']),
            'recommended_count': min(20, int(counts['due'])), 'today_answers': today.get('practice', 0), 'today_reviews': today.get('review', 0),
            'concepts': list(concepts), 'trend': [{'day': day, 'count': count} for day, count in trend.items()], 'trend_truncated': len(events) > 5000,
            'scheduler_version': scheduler.VERSION, 'knowledge_version': bkt.VERSION,
            'cold_start': 'Default, unpersonalized parameters. Repeated questions are correlated; estimates are not exam scores.'}


async def cards(user_id, mode='due', notebook_id=None, card_id=None):
    from app.services.grading_service import public_quiz
    clauses = {'due': ' AND c.due_at<=%s', 'wrong': ' AND c.wrong_count>0', 'favorites': ' AND c.favorite=1', 'all': ''}
    if mode not in clauses:
        raise HTTPException(422, '复习列表类型无效')
    args = (user_id, user_id, sql_time(utcnow())) if mode == 'due' else (user_id, user_id)
    notebook_clause = ''
    card_clause = ''
    async with transaction() as cur:
        if notebook_id:
            await cur.execute('SELECT notebook_id FROM learning_notebooks WHERE notebook_id=%s AND user_id=%s', (notebook_id, user_id))
            if not await cur.fetchone():
                raise HTTPException(404, '错题本不存在')
            notebook_clause = ' AND EXISTS(SELECT 1 FROM learning_notebook_items i WHERE i.notebook_id=%s AND i.user_id=c.user_id AND i.quiz_id=c.quiz_id AND i.question_id=c.question_id)'
            args = (*args, notebook_id)
        if card_id:
            card_clause = ' AND c.card_id=%s'
            args = (*args, card_id)
        await cur.execute('SELECT c.*,q.questions_json,p.label,p.mastery,p.attempts,p.mapping_confidence FROM learning_cards c '
                          'JOIN quiz_sessions q ON c.quiz_id=q.quiz_id JOIN learning_concepts p ON c.user_id=p.user_id AND c.concept_id=p.concept_id '
                          'WHERE c.user_id=%s AND q.user_id=%s' + clauses[mode] + notebook_clause + card_clause + ' ORDER BY c.due_at,c.card_id LIMIT 50', args)
        rows = await cur.fetchall()
    result = []
    for row in rows:
        question = next((q for q in decoded(row['questions_json']) if q['id'] == row['question_id']), None)
        if question:
            result.append({key: row[key] for key in ('card_id', 'quiz_id', 'version', 'diagnosis', 'wrong_count', 'label', 'mastery', 'attempts', 'mapping_confidence')} |
                          {'favorite': bool(row['favorite']), 'last_correct': bool(row['last_correct']), 'due_at': iso(row['due_at']), 'question': public_quiz({'questions': [question]})['questions'][0]})
    if card_id and not result:
        raise HTTPException(404, '复习记录不存在')
    return result


async def submit_review(card_id, user_id, request, *, context=None, verdict=None):
    from app.services.grading_service import grade_answer
    now = utcnow()
    async with transaction() as cur:
        if context:
            from app.repositories import job_repository as jobs
            job = await jobs.running(cur, context.task_id, context.lease_token)
            if job['kind'] != 'grade' or job['user_id'] != user_id or job['payload_json'] != context.payload:
                raise jobs.TaskLeaseLost()
        await cur.execute('SELECT * FROM learning_cards WHERE card_id=%s AND user_id=%s FOR UPDATE', (card_id, user_id))
        card = await cur.fetchone()
        if not card:
            raise HTTPException(404, '复习记录不存在')
        await cur.execute('SELECT questions_json FROM quiz_sessions WHERE quiz_id=%s AND user_id=%s', (card['quiz_id'], user_id))
        quiz = await cur.fetchone()
        question = next((q for q in decoded(quiz['questions_json']) if q['id'] == card['question_id']), None) if quiz else None
        if not question:
            raise HTTPException(404, '练习题目不存在')
        record = grade_answer(question, request.selected_answers, request.duration_ms, verdict=verdict)
        await cur.execute('SELECT event_json FROM learning_events WHERE user_id=%s AND card_id=%s AND version=%s', (user_id, card_id, request.version))
        previous = await cur.fetchone()
        if previous:
            result = decoded(previous['event_json'])
            if result['record']['selected_answers'] != record['selected_answers']:
                raise HTTPException(409, '这轮复习已提交其他答案，请刷新记录')
        else:
            if card['version'] != request.version:
                raise HTTPException(409, '复习状态已更新，请刷新后继续')
            if card['due_at'] > sql_time(now):
                raise HTTPException(409, '尚未到复习时间，可以先查看原练习解析')
            mapping = bkt.concept_mapping(question, card['quiz_id'])
            knowledge = await observe(cur, user_id, mapping, record['is_correct'], now)
            schedule = scheduler.review(decoded(card['card_json']), card_id, record['is_correct'], now)
            due = datetime.fromisoformat(schedule['card']['due'])
            result = {'record': record, 'knowledge': knowledge, 'schedule': schedule, 'version': card['version'] + 1, 'due_at': due.isoformat()}
            await cur.execute('UPDATE learning_cards SET card_json=%s,due_at=%s,version=version+1,last_correct=%s,wrong_count=wrong_count+%s,updated_at=%s WHERE card_id=%s AND user_id=%s',
                              (encoded(schedule['card']), sql_time(due), record['is_correct'], int(not record['is_correct']), sql_time(now), card_id, user_id))
            await cur.execute('INSERT INTO learning_events(user_id,card_id,version,source,event_json,created_at) VALUES(%s,%s,%s,\'review\',%s,%s)',
                              (user_id, card_id, request.version, encoded(result), sql_time(now)))
        if context:
            await jobs.publish_result(cur, job, {'quiz_id': card['quiz_id'], 'question_id': card['question_id'], 'card_id': card_id, 'version': request.version})
    return {key: result[key] for key in ('record', 'version', 'due_at', 'knowledge')} | {'card_id': card_id, 'quiz_id': card['quiz_id'], 'replayed': bool(previous), 'question': await visible_question(question, user_id)}


async def review_result(card_id, version, user_id):
    async with transaction() as cur:
        await cur.execute('SELECT e.event_json,c.question_id,c.quiz_id,q.questions_json FROM learning_events e '
                          'JOIN learning_cards c ON e.card_id=c.card_id AND e.user_id=c.user_id '
                          'JOIN quiz_sessions q ON c.quiz_id=q.quiz_id AND c.user_id=q.user_id '
                          "WHERE e.user_id=%s AND e.card_id=%s AND e.version=%s AND e.source='review'", (user_id, card_id, version))
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, '这轮复习记录不存在')
    event = decoded(row['event_json'])
    question = next(q for q in decoded(row['questions_json']) if q['id'] == row['question_id'])
    return {key: event[key] for key in ('record', 'version', 'due_at', 'knowledge')} | {'card_id': card_id, 'quiz_id': row['quiz_id'], 'replayed': True, 'question': await visible_question(question, user_id)}


async def update_card(card_id, user_id, settings):
    async with transaction() as cur:
        await cur.execute('SELECT card_id FROM learning_cards WHERE card_id=%s AND user_id=%s FOR UPDATE', (card_id, user_id))
        if not await cur.fetchone():
            raise HTTPException(404, '复习记录不存在')
        if 'favorite' in settings.model_fields_set and settings.favorite is not None:
            await cur.execute('UPDATE learning_cards SET favorite=%s WHERE card_id=%s AND user_id=%s', (settings.favorite, card_id, user_id))
        if 'diagnosis' in settings.model_fields_set:
            await cur.execute('UPDATE learning_cards SET diagnosis=%s WHERE card_id=%s AND user_id=%s', (settings.diagnosis, card_id, user_id))
