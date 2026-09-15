import uuid
from fastapi import APIRouter, Depends, Header
from app.core.auth import get_current_user
from app.models.common import ApiResponse
from app.models.companion import CharacterId, CompanionTurn, MemoryUpdate, ResetConversation
from app.repositories import companion_repository as repository

router = APIRouter(prefix='/companions', tags=['companions'])


@router.get('/{identity}')
async def detail(identity: CharacterId, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await repository.detail(user_id, identity))


@router.post('/{identity}/turns')
async def turn(identity: CharacterId, request: CompanionTurn, user_id: int = Depends(get_current_user), idempotency_key: str | None = Header(default=None)):
    return ApiResponse.success(data=await repository.admit(user_id, identity, request, idempotency_key or uuid.uuid4().hex))


@router.put('/{identity}/memories')
async def memories(identity: CharacterId, request: MemoryUpdate, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await repository.set_memories(user_id, identity, request))


@router.post('/{identity}/reset')
async def reset(identity: CharacterId, request: ResetConversation, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await repository.reset(user_id, identity, request))
