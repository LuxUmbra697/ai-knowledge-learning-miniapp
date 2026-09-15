"""知识库文档路由"""

from fastapi import APIRouter, Depends, UploadFile, File, Query, Header

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.core.exceptions import KnowledgeBaseError
from app.models.common import ApiResponse
from app.models.evidence import RetrievalRequest, evidence_from_row
from app.repositories import rag_index_repository
from app.services import knowledge_service, vector_store_service, learning_task_service

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post('/ask', response_model=ApiResponse)
async def ask(request: RetrievalRequest, user_id: int = Depends(get_current_user), idempotency_key: str | None = Header(None)):
    task = await learning_task_service.create_answer(user_id, request, idempotency_key)
    result = await learning_task_service.wait_result(task['task_id'], user_id)
    return ApiResponse.success(data=result)


@router.post('/ask/async', response_model=ApiResponse)
async def ask_async(request: RetrievalRequest, user_id: int = Depends(get_current_user), idempotency_key: str | None = Header(None)):
    return ApiResponse.success(data=await learning_task_service.create_answer(user_id, request, idempotency_key))


@router.post('/retrieve', response_model=ApiResponse)
async def retrieve(request: RetrievalRequest, user_id: int = Depends(get_current_user), idempotency_key: str | None = Header(None)):
    task = await learning_task_service.create_retrieval(user_id, request, idempotency_key)
    return ApiResponse.success(data=await learning_task_service.wait_result(task['task_id'], user_id, 30))


@router.get('/documents/{doc_id}/chunks', response_model=ApiResponse)
async def document_chunks(doc_id: str, page: int = Query(1, ge=1), user_id: int = Depends(get_current_user)):
    rows = await rag_index_repository.scoped_chunks(user_id, [doc_id], vector_store_service.index_version())
    rows.sort(key=lambda row: row['metadata'].get('chunk_index', 0))
    return ApiResponse.success(data={'items': [evidence_from_row(row, row['chunk_id']).model_dump() for row in rows[(page-1)*20:page*20]],
                                     'total': len(rows), 'page': page})


@router.get('/documents/{doc_id}/chunks/{chunk_id}', response_model=ApiResponse)
async def document_chunk(doc_id: str, chunk_id: str, revision: int = Query(..., ge=1), user_id: int = Depends(get_current_user)):
    row = await rag_index_repository.get_chunk(user_id, doc_id, chunk_id, revision)
    return ApiResponse.success(data=evidence_from_row(row, chunk_id).model_dump())


@router.post('/documents/{doc_id}/reindex', response_model=ApiResponse)
async def reindex_document(doc_id: str, user_id: int = Depends(get_current_user)):
    return ApiResponse.success(data=await knowledge_service.reindex_document(user_id, doc_id))


@router.post("/documents", response_model=ApiResponse)
async def upload_document(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user),
):
    content = await file.read(get_settings().kb_max_file_size_mb * 1024 * 1024 + 1)
    if len(content) > get_settings().kb_max_file_size_mb * 1024 * 1024:
        raise KnowledgeBaseError('文件大小超过限制')
    result = await knowledge_service.handle_upload(
        user_id=user_id, filename=file.filename or "unknown", content=content
    )
    return ApiResponse.success(data=result.model_dump())


@router.get("/documents", response_model=ApiResponse)
async def list_documents(user_id: int = Depends(get_current_user)):
    result = await knowledge_service.list_documents(user_id)
    return ApiResponse.success(data=result.model_dump())


@router.get("/documents/{doc_id}", response_model=ApiResponse)
async def get_document_status(doc_id: str, user_id: int = Depends(get_current_user)):
    result = await knowledge_service.get_document_status(user_id, doc_id)
    return ApiResponse.success(data=result.model_dump())


@router.delete("/documents/{doc_id}", response_model=ApiResponse)
async def delete_document(doc_id: str, user_id: int = Depends(get_current_user)):
    await knowledge_service.delete_document(user_id, doc_id)
    return ApiResponse.success()
