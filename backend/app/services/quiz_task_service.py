"""Owned private text practice on the shared durable queue. Legacy image/web paths stay explicit."""
import uuid

from fastapi import HTTPException

from app.core.security import check_content
from app.core.exceptions import ContentFilterError
from app.llm.quiz_chain import generate_quiz
from app.models.quiz import QuizGenerateResponse, QuizTaskStatusResponse
from app.repositories import job_repository as jobs, quiz_repository, rag_index_repository as index
from app.services import vector_store_service as vectors, retrieval_service, rag_service


async def create(req, user_id, key=None):
    if not user_id:
        raise HTTPException(401, '请先登录')
    if not req.doc_id or req.generate_images:
        raise HTTPException(422, '此任务入口仅接收知识库文字练习')
    if not check_content(req.user_input):
        raise ContentFilterError('输入内容包含不当内容，请修改后重试')
    rows = await index.scoped_chunks(user_id, [req.doc_id], vectors.index_version())
    if not rows:
        raise HTTPException(409, '材料没有可用片段，请重新建立索引')
    scope = [list(item) for item in sorted({(row['doc_id'], row['revision'], row['index_version']) for row in rows})]
    payload = dict(query=req.user_input, question_count=req.question_count, difficulty=req.difficulty,
                   doc_ids=[req.doc_id], scope=scope, mode='rerank')
    return await jobs.enqueue(user_id, 'quiz', payload, key or uuid.uuid4().hex)


async def run(context):
    from app.services.job_handlers import validate_scope
    await validate_scope(context)
    payload = context.payload
    source = context.checkpoints.get('quiz_sources')
    if source is None:
        result = await retrieval_service.retrieve(context.user_id, payload['doc_ids'], payload['query'],
                                                  mode=payload['mode'], context=context)
        source = rag_service.serialize_context(result)
        await context.checkpoint('quiz_sources', source)
    output = await generate_quiz(payload['query'], payload['question_count'], payload['difficulty'],
                                 search_context=source, private_source=True, context=context)
    await context.checkpoint('quiz_validated', {'question_count': len(output.questions)})
    return await quiz_repository.publish_generated_quiz(context, output)


async def result_response(reference, user_id):
    detail = await quiz_repository.get_quiz_detail(reference['quiz_id'], user_id)
    if detail is None:
        raise HTTPException(404, '练习不存在')
    return QuizGenerateResponse.model_validate(detail)


async def status(task_id, user_id):
    task = await jobs.get_owned(task_id, user_id)
    if task['kind'] != 'quiz':
        raise HTTPException(404, '练习任务不存在')
    result = await result_response(task['result'], user_id) if task['status'] == 'completed' else None
    state = {'queued': 'pending', 'staging': 'pending', 'cancelled': 'failed'}.get(task['status'], task['status'])
    message = task.get('error_message') or ('练习任务已取消' if task['status'] == 'cancelled' else None)
    return QuizTaskStatusResponse(task_id=task_id, status=state, stage=task['stage'], result=result, error_message=message)
