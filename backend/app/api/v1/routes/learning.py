"""Owned learning state and authoritative, optimistic-versioned reviews."""
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query

from app.core.auth import get_current_user
from app.models.common import ApiResponse
from app.models.learning_path import PathUpdate, PlanConfirm
from app.models.tutor import TutorCreate, TutorPracticeConfirm, TutorTurn
from app.repositories import tutor_repository
from app.services import learning_path_service as planning
from app.services import learning_state_service as service
from app.services import notebook_service as books
from app.services import tutor_service as tutor

router = APIRouter(prefix='/learning', tags=['learning'])


@router.get('/path')
async def learning_path(user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await planning.get_path(user_id))


@router.put('/path')
async def set_learning_path(req: PathUpdate, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await planning.update_path(user_id, req))


@router.get('/plans/preview')
async def preview_plan(minutes: int = Query(15, ge=5, le=60), timezone: str = Query('Asia/Shanghai', max_length=64), user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await planning.preview(user_id, minutes, timezone))


@router.get('/plans')
async def plans(user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data={'items': await planning.list_plans(user_id)})


@router.post('/plans')
async def confirm_plan(req: PlanConfirm, user_id: int = Depends(get_current_user), idempotency_key: str | None = Header(default=None)):
    return ApiResponse.success(data=await planning.confirm(user_id, req, idempotency_key))


@router.get('/plans/{plan_id}')
async def plan_detail(plan_id: str, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await planning.detail(plan_id, user_id))


@router.put('/plans/{plan_id}/read/{item_id}')
async def plan_read(plan_id: str, item_id: str, user_id: int = Depends(get_current_user)):
    await planning.mark_read(plan_id, user_id, item_id)
    return ApiResponse.success()


@router.get('/cards/{card_id}')
async def card_detail(card_id: str, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=(await service.cards(user_id, 'all', card_id=card_id))[0])


@router.get('/tutor/context')
async def tutor_context(quiz_id: str = Query(max_length=64), question_id: str = Query(max_length=64), user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await tutor.question_context(user_id, quiz_id, question_id))


@router.get('/tutor/sessions')
async def tutor_sessions(user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data={'items': await tutor_repository.list_sessions(user_id)})


@router.post('/tutor/sessions')
async def start_tutor(req: TutorCreate, user_id: int = Depends(get_current_user), idempotency_key: str | None = Header(default=None)):
    return ApiResponse.success(data=await tutor.create(user_id, req, idempotency_key))


@router.get('/tutor/sessions/{session_id}')
async def get_tutor(session_id: str, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await tutor.detail(session_id, user_id))


@router.post('/tutor/sessions/{session_id}/turns')
async def tutor_turn(session_id: str, req: TutorTurn, user_id: int = Depends(get_current_user), idempotency_key: str | None = Header(default=None)):
    return ApiResponse.success(data=await tutor.turn(session_id, user_id, req, idempotency_key))


@router.delete('/tutor/sessions/{session_id}')
async def delete_tutor(session_id: str, user_id: int = Depends(get_current_user)):
    await tutor_repository.delete(session_id, user_id)
    return ApiResponse.success()


@router.post('/tutor/sessions/{session_id}/turns/{number}/practice')
async def tutor_practice(session_id: str, number: int, req: TutorPracticeConfirm, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await tutor.confirm_practice(session_id, user_id, number, req))


@router.post('/cards/{card_id}/answer/async')
async def review_with_model(card_id: str, req: service.ReviewSubmission, user_id: int = Depends(get_current_user), idempotency_key: str | None = Header(default=None)):
    from app.services.written_grade_service import submit_review
    return ApiResponse.success(data=await submit_review(card_id, user_id, req, idempotency_key))


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
