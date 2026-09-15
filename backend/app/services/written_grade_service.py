"""Owned written-answer admission and atomic publication on the durable worker."""
import re
import uuid

from fastapi import HTTPException

from app.llm.written_grading import evaluate
from app.repositories import job_repository as jobs
from app.repositories.rag_index_repository import transaction
from app.services import grading_service as grading
from app.services import learning_state_service as learning


async def owned_question(cur, user_id, quiz_id, question_id):
    await cur.execute('SELECT questions_json FROM quiz_sessions WHERE quiz_id=%s AND user_id=%s', (quiz_id, user_id))
    row = await cur.fetchone()
    question = next((q for q in grading.decode_json(row['questions_json']) if q['id'] == question_id), None) if row else None
    if question is None:
        raise HTTPException(404, '练习题目不存在')
    return question


async def submit(quiz_id, user_id, submission, key=None, *, card_id=None, version=None):
    async with transaction() as cur:
        question = await owned_question(cur, user_id, quiz_id, submission.question_id)
    if question['type'] != 'written':
        if card_id:
            request = learning.ReviewSubmission(version=version, selected_answers=submission.selected_answers, duration_ms=submission.duration_ms)
            return await learning.submit_review(card_id, user_id, request)
        return await grading.submit_question(quiz_id, user_id, submission)
    selected = grading.validate_selection(question, submission.selected_answers)
    key = key or uuid.uuid4().hex
    if not re.fullmatch(r'[a-zA-Z0-9:_-]{8,100}', key):
        raise HTTPException(422, '请求标识无效')
    async with transaction() as cur:
        # The same owner lock as queue admission serializes competing devices before spending.
        await cur.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (user_id,))
        if not await cur.fetchone():
            raise HTTPException(401, '账户不存在')
        resource = {'quiz_id': quiz_id, 'question_id': submission.question_id, 'card_id': card_id, 'version': version}
        if card_id:
            await cur.execute('SELECT * FROM learning_cards WHERE card_id=%s AND user_id=%s', (card_id, user_id))
            card = await cur.fetchone()
            if not card or card['quiz_id'] != quiz_id or card['question_id'] != submission.question_id:
                raise HTTPException(404, '复习记录不存在')
            await cur.execute("SELECT event_json FROM learning_events WHERE card_id=%s AND user_id=%s AND version=%s AND source='review'", (card_id, user_id, version))
            previous = await cur.fetchone()
            previous = grading.decode_json(previous['event_json'])['record'] if previous else None
            if not previous and (card['version'] != version or card['due_at'] > learning.sql_time(learning.utcnow())):
                raise HTTPException(409, '复习状态已变化或尚未到期，请刷新后继续')
        else:
            await cur.execute('SELECT record_json FROM quiz_question_attempts WHERE quiz_id=%s AND user_id=%s AND question_id=%s',
                              (quiz_id, user_id, submission.question_id))
            previous = await cur.fetchone()
            previous = grading.decode_json(previous['record_json']) if previous else None
        if previous:
            if previous['selected_answers'] != selected:
                raise HTTPException(409, '该题已提交其他答案，不能覆盖原记录')
            return {'completed': True, **resource}
        await cur.execute("SELECT j.* FROM learning_jobs j LEFT JOIN learning_job_request_keys k ON "
                          "k.task_id=j.task_id AND k.user_id=j.user_id AND k.kind=j.kind "
                          "WHERE j.user_id=%s AND j.kind='grade' AND (j.idempotency_key=%s OR k.idempotency_key=%s) LIMIT 1",
                          (user_id, key, key))
        bound = jobs.decode(await cur.fetchone())
        if bound:
            if any(bound['payload_json'].get(field) != value for field, value in resource.items()) or bound['payload_json']['selected_answers'] != selected:
                raise HTTPException(409, '请求标识已用于不同答案')
            return jobs.public(bound, True)
        await cur.execute("SELECT * FROM learning_jobs WHERE user_id=%s AND kind='grade' AND "
                          "JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.quiz_id'))=%s AND "
                          "JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.question_id'))=%s ORDER BY created_at DESC LIMIT 100",
                          (user_id, quiz_id, submission.question_id))
        for row in await cur.fetchall():
            job = jobs.decode(row)
            payload = job['payload_json']
            if any(payload.get(field) != value for field, value in resource.items()):
                continue
            same_key = job['idempotency_key'] == key
            if same_key or job['status'] in ('queued', 'running'):
                if payload['selected_answers'] != selected:
                    raise HTTPException(409, '此题已有评阅任务，请等待或取消后再提交')
                if not same_key:
                    await jobs.bind_request_key(cur, user_id, 'grade', key, job['task_id'])
                return jobs.public(job, True)
        payload = {**resource, 'selected_answers': selected, 'duration_ms': submission.duration_ms, 'title': question['stem'][:80]}
        return await jobs.insert(cur, user_id, 'grade', payload, key)


async def submit_review(card_id, user_id, request, key=None):
    async with transaction() as cur:
        await cur.execute('SELECT quiz_id,question_id FROM learning_cards WHERE card_id=%s AND user_id=%s', (card_id, user_id))
        card = await cur.fetchone()
    if card is None:
        raise HTTPException(404, '复习记录不存在')
    submission = grading.AnswerSubmission(question_id=card['question_id'], selected_answers=request.selected_answers, duration_ms=request.duration_ms)
    return await submit(card['quiz_id'], user_id, submission, key, card_id=card_id, version=request.version)


async def run(context):
    payload = context.payload
    async with transaction() as cur:
        question = await owned_question(cur, context.user_id, payload['quiz_id'], payload['question_id'])
    if question['type'] != 'written':
        raise HTTPException(409, '题型发生变化，未发布评阅结果')
    verdict = await evaluate(question, payload['selected_answers'][0], context)
    await context.checkpoint('written_grade_validated', {'criteria_count': len(verdict['grading']['criteria'])})
    if payload.get('card_id'):
        request = learning.ReviewSubmission(version=payload['version'], selected_answers=payload['selected_answers'], duration_ms=payload['duration_ms'])
        await learning.submit_review(payload['card_id'], context.user_id, request, context=context, verdict=verdict)
    else:
        request = grading.AnswerSubmission(question_id=payload['question_id'], selected_answers=payload['selected_answers'], duration_ms=payload['duration_ms'])
        await grading.submit_question(payload['quiz_id'], context.user_id, request, context=context, verdict=verdict)
    return {key: payload[key] for key in ('quiz_id', 'question_id', 'card_id', 'version')}
