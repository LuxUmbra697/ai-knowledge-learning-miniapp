"""Quiz HTTP compatibility and admission. All new execution belongs to durable workers."""
from fastapi import HTTPException

from app.models.quiz import QuizGenerateRequest, QuizGenerateResponse, QuizTaskCreateResponse, QuizTaskStatusResponse
from app.repositories import task_repository
from app.services import quiz_task_service
from app.services import learning_task_service


async def handle_quiz_generate(req: QuizGenerateRequest, user_id: int | None = None, key: str | None = None) -> QuizGenerateResponse:
    task = await quiz_task_service.create(req, user_id, key)
    reference = await learning_task_service.wait_result(task['task_id'], user_id, seconds=60)
    return await quiz_task_service.result_response(reference, user_id)


async def create_quiz_task(req: QuizGenerateRequest, user_id: int | None = None, key: str | None = None) -> QuizTaskCreateResponse:
    task = await quiz_task_service.create(req, user_id, key)
    return QuizTaskCreateResponse(task_id=task['task_id'])


async def get_quiz_task_status(task_id: str, user_id: int) -> QuizTaskStatusResponse:
    if task_id.startswith('job_'):
        return await quiz_task_service.status(task_id, user_id)
    row = await task_repository.get_task(task_id, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail='任务不存在')
    state = row['status']
    message = row.get('error_message')
    if state in ('pending', 'running'):
        state, message = 'failed', '此旧版任务已中断，请从学习首页重新生成；系统未自动重复调用模型'
    result = QuizGenerateResponse.model_validate(row['result_json']) if state == 'completed' and row.get('result_json') else None
    return QuizTaskStatusResponse(task_id=task_id, status=state, result=result, error_message=message)
