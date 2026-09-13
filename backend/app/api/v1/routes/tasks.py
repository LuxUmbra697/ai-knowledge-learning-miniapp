"""Authenticated task monitoring and cancellation; no arbitrary task payload endpoint."""
from fastapi import APIRouter, Depends

from app.core.auth import get_current_user
from app.models.common import ApiResponse
from app.repositories import job_repository

router = APIRouter(prefix='/learning/tasks', tags=['learning-tasks'])


@router.get('')
async def list_tasks(user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data={'items': await job_repository.list_owned(user_id)})


@router.get('/{task_id}')
async def get_task(task_id: str, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await job_repository.get_owned(task_id, user_id))


@router.post('/{task_id}/cancel')
async def cancel_task(task_id: str, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await job_repository.cancel(task_id, user_id))
