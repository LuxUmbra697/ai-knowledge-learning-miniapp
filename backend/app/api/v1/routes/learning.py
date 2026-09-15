"""Owned learning state and authoritative, optimistic-versioned reviews."""
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_user
from app.models.common import ApiResponse
from app.services import learning_state_service as service
from app.services import notebook_service as books

router = APIRouter(prefix='/learning', tags=['learning'])


@router.get('/notebooks')
async def notebooks(user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data={'items': await books.list_notebooks(user_id)})


@router.post('/notebooks')
async def create_notebook(req: books.NotebookName, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await books.create(user_id, req))


@router.put('/notebooks/{notebook_id}')
async def rename_notebook(notebook_id: str, req: books.NotebookRename, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await books.rename(notebook_id, user_id, req))


@router.delete('/notebooks/{notebook_id}')
async def delete_notebook(notebook_id: str, version: int = Query(ge=1), user_id: int = Depends(get_current_user)):
    await books.delete(notebook_id, user_id, version)
    return ApiResponse.success()


@router.get('/notebooks/{notebook_id}/cards')
async def notebook_cards(notebook_id: str, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data={'items': await books.items(notebook_id, user_id), 'limit': 50})


@router.put('/notebooks/{notebook_id}/cards/{card_id}')
async def add_notebook_card(notebook_id: str, card_id: str, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await books.add(notebook_id, user_id, card_id))


@router.post('/notebooks/{notebook_id}/questions')
async def add_notebook_question(notebook_id: str, req: books.NotebookQuestion, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await books.add_question(notebook_id, user_id, req))


@router.delete('/notebooks/{notebook_id}/cards/{card_id}')
async def remove_notebook_card(notebook_id: str, card_id: str, user_id: int = Depends(get_current_user)):
    await books.remove(notebook_id, user_id, card_id)
    return ApiResponse.success()


@router.get('/summary')
async def summary(timezone: str = Query('Asia/Shanghai', max_length=64), user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await service.summary(user_id, timezone))


@router.get('/cards')
async def cards(mode: Literal['due', 'wrong', 'favorites', 'all'] = 'due', user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data={'items': await service.cards(user_id, mode), 'limit': 50})


@router.post('/cards/{card_id}/answer')
async def answer(card_id: str, req: service.ReviewSubmission, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await service.submit_review(card_id, user_id, req))


@router.put('/cards/{card_id}')
async def update(card_id: str, req: service.CardSettings, user_id: int = Depends(get_current_user)):
    await service.update_card(card_id, user_id, req)
    return ApiResponse.success()


@router.get('/cards/{card_id}/events/{version}')
async def result(card_id: str, version: int, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await service.review_result(card_id, version, user_id))
