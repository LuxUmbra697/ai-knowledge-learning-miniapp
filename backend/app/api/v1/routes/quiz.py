"""出题路由"""

from fastapi import APIRouter, Depends

from app.core.auth import get_current_user
from app.models.common import ApiResponse
from app.models.quiz import QuizGenerateRequest
from app.services.grading_service import AnswerSubmission, public_quiz, submit_question
from app.services.quiz_service import (
    handle_quiz_generate,
    create_quiz_task,
    get_quiz_task_status,
)

router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.post("/generate", response_model=ApiResponse)
async def quiz_generate(
    req: QuizGenerateRequest,
    user_id: int = Depends(get_current_user),
):
    result = await handle_quiz_generate(req, user_id=user_id)
    return ApiResponse.success(data=public_quiz(result.model_dump()))


@router.post("/generate/async", response_model=ApiResponse)
async def quiz_generate_async(
    req: QuizGenerateRequest,
    user_id: int = Depends(get_current_user),
):
    """异步创建出题任务，立即返回 task_id"""
    result = await create_quiz_task(req, user_id=user_id)
    return ApiResponse.success(data=result.model_dump())


@router.get("/task/{task_id}", response_model=ApiResponse)
async def quiz_task_status(task_id: str, user_id: int = Depends(get_current_user)):
    """轮询查询任务状态"""
    result = await get_quiz_task_status(task_id, user_id)
    data = result.model_dump()
    if data.get("result"):
        data["result"] = public_quiz(data["result"])
    return ApiResponse.success(data=data)


@router.post("/{quiz_id}/answer", response_model=ApiResponse)
async def answer_question(quiz_id: str, req: AnswerSubmission, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await submit_question(quiz_id, user_id, req))
