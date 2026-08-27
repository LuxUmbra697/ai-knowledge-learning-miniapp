"""用户路由"""

from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_user
from app.models.common import ApiResponse
from app.models.user import LoginRequest, UpdateProfileRequest
from app.services import user_service, history_service

router = APIRouter(prefix="/user", tags=["user"])


@router.post("/login", response_model=ApiResponse)
async def login(req: LoginRequest):
    result = await user_service.handle_login(req.code)
    return ApiResponse.success(data=result.model_dump())


@router.get("/profile", response_model=ApiResponse)
async def get_profile(user_id: int = Depends(get_current_user)):
    result = await user_service.get_profile(user_id)
    return ApiResponse.success(data=result.model_dump())


@router.put("/profile", response_model=ApiResponse)
async def update_profile(
    req: UpdateProfileRequest,
    user_id: int = Depends(get_current_user),
):
    await user_service.update_profile(user_id, req.nickname, req.avatar_url)
    return ApiResponse.success()


@router.get("/quizzes", response_model=ApiResponse)
async def get_quiz_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    user_id: int = Depends(get_current_user),
):
    result = await history_service.get_quiz_history(user_id, page, page_size)
    return ApiResponse.success(data=result.model_dump())


@router.get("/quizzes/{quiz_id}", response_model=ApiResponse)
async def get_quiz_detail(
    quiz_id: str,
    user_id: int = Depends(get_current_user),
):
    result = await history_service.get_quiz_detail(quiz_id, user_id)
    if result is None:
        return ApiResponse.error(code=4004, message="闯关记录不存在")
    return ApiResponse.success(data=result.model_dump())
