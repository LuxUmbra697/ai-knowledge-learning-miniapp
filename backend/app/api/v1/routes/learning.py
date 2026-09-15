"""Owned learning state and authoritative, optimistic-versioned reviews."""
from typing import Literal
from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_user
from app.models.common import ApiResponse
from app.services import learning_state_service as service

router = APIRouter(prefix='/learning', tags=['learning'])


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
