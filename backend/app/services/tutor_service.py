"""Conversation admission and source checks, without model-selected authority."""
import uuid

from fastapi import HTTPException

from app.repositories import rag_index_repository as index
from app.repositories import tutor_repository as repository
from app.services import vector_store_service as vectors


async def question_context(user_id, quiz_id, question_id):
    async with index.transaction() as cur:
        await cur.execute('SELECT card_id FROM learning_cards WHERE user_id=%s AND quiz_id=%s AND question_id=%s AND wrong_count>0', (user_id, quiz_id, question_id))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, '错题记录不存在')
        return {'card_id': row['card_id']}


async def practice_material(user_id, card_id):
    async with index.transaction() as cur:
        await cur.execute('SELECT c.quiz_id,c.question_id,c.diagnosis,q.questions_json FROM learning_cards c '
                          'JOIN quiz_sessions q ON q.quiz_id=c.quiz_id AND q.user_id=c.user_id '
                          'WHERE c.card_id=%s AND c.user_id=%s AND c.wrong_count>0', (card_id, user_id))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, '错题记录不存在')
        await cur.execute("SELECT event_json FROM learning_events WHERE card_id=%s AND user_id=%s AND JSON_UNQUOTE(JSON_EXTRACT(event_json,'$.record.is_correct'))='false' "
                          'ORDER BY created_at DESC,version DESC LIMIT 1', (card_id, user_id))
        event = await cur.fetchone()
        question = next((q for q in repository.decoded(row['questions_json']) if q['id'] == row['question_id']), None)
        if not event or not question:
            raise HTTPException(404, '错题依据不完整')
        record = repository.decoded(event['event_json'])['record']
        return {'question': question, 'record': record, 'quiz_id': row['quiz_id'], 'confirmed_diagnosis': row['diagnosis']}


async def scope(user_id, doc_ids):
    if not doc_ids:
        return []
    rows = await index.scoped_chunks(user_id, doc_ids, vectors.index_version())
    return [list(value) for value in sorted({(row['doc_id'], row['revision'], row['index_version']) for row in rows})]


async def validate_session(session, user_id):
    config = session['config_json']
    if await scope(user_id, config['doc_ids']) != config['scope']:
        raise HTTPException(409, '学习材料已变化，请创建新的辅导会话')
    if config.get('card_id'):
        await practice_material(user_id, config['card_id'])


async def create(user_id, request, key=None):
    config = request.model_dump()
    if request.mode == 'diagnosis':
        source = await practice_material(user_id, request.card_id)
        config['doc_ids'] = sorted({citation['doc_id'] for citation in source['question'].get('citations', [])
                                    if citation.get('doc_id') and citation.get('status') == 'verified'})
        if len(config['doc_ids']) > 3:
            raise HTTPException(422, '错题引用超出本次辅导材料上限')
    config['scope'] = await scope(user_id, config['doc_ids'])
    return await repository.create(user_id, request, config, key or uuid.uuid4().hex)


async def detail(session_id, user_id):
    session = await repository.get(session_id, user_id)
    await validate_session(session, user_id)
    material = await practice_material(user_id, session['config_json']['card_id']) if session['config_json'].get('card_id') else None
    return {**repository.public(session), 'turns': await repository.turns(session_id, user_id),
            'confirmed_diagnosis': material['confirmed_diagnosis'] if material else None}


async def turn(session_id, user_id, request, key=None):
    session = await repository.get(session_id, user_id)
    await validate_session(session, user_id)
    return await repository.admit(session_id, user_id, request, key or uuid.uuid4().hex)


async def confirm_practice(session_id, user_id, number, request):
    from app.models.quiz import QuizGenerateRequest
    from app.services import quiz_task_service
    from app.services.tutor_tools import PracticeArguments
    session = await detail(session_id, user_id)
    if session['version'] != request.version:
        raise HTTPException(409, '辅导进度已变化，请刷新后确认练习建议')
    turn = next((item for item in session['turns'] if item['number'] == number), None)
    proposal = turn['response'].get('practice') if turn else None
    if not proposal or not proposal.get('requires_confirmation') or proposal.get('created'):
        raise HTTPException(404, '这轮辅导没有可确认的练习建议')
    args = PracticeArguments.model_validate({name: proposal[name] for name in ('focus', 'count')})
    expected_doc = session['doc_ids'][0] if session['doc_ids'] else None
    if proposal.get('doc_id') != expected_doc:
        raise HTTPException(409, '练习建议的资料范围已变化')
    command = QuizGenerateRequest(user_input=args.focus, question_count=args.count, doc_id=expected_doc)
    return await quiz_task_service.create(command, user_id, f'tutor_practice_{session_id}_{number}')
