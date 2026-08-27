"""知识库文档业务服务：上传、解析、状态查询、删除"""

from __future__ import annotations

import asyncio
import os
import uuid

import structlog

from app.core.config import get_settings
from app.core.exceptions import KnowledgeBaseError
from app.models.knowledge import (
    KnowledgeDocumentItem,
    KnowledgeListResponse,
    KnowledgeStatusResponse,
    KnowledgeUploadResponse,
)
from app.repositories import knowledge_repository
from app.services import document_loader_service, vector_store_service

logger = structlog.get_logger()

SUPPORTED_EXTENSIONS = {"pdf", "docx", "md", "txt"}


def _get_extension(filename: str) -> str:
    _, ext = os.path.splitext(filename)
    return ext.lstrip(".").lower()


async def handle_upload(user_id: int, filename: str, content: bytes) -> KnowledgeUploadResponse:
    """校验并保存上传的文档，后台异步解析处理"""
    settings = get_settings()

    file_type = _get_extension(filename)
    if file_type not in SUPPORTED_EXTENSIONS:
        raise KnowledgeBaseError(
            f"不支持的文件格式：{file_type or '未知'}，仅支持 PDF/Word/Markdown/文本文件"
        )

    max_size_bytes = settings.kb_max_file_size_mb * 1024 * 1024
    if len(content) > max_size_bytes:
        raise KnowledgeBaseError(f"文件大小超过限制（最大 {settings.kb_max_file_size_mb}MB）")

    existing_count = await knowledge_repository.count_documents(user_id)
    if existing_count >= settings.kb_max_documents_per_user:
        raise KnowledgeBaseError(
            f"知识库文档数量已达上限（最多 {settings.kb_max_documents_per_user} 篇），请先删除部分文档"
        )

    doc_id = f"doc_{uuid.uuid4().hex[:12]}"

    os.makedirs(settings.kb_upload_dir, exist_ok=True)
    file_path = os.path.join(settings.kb_upload_dir, f"{doc_id}.{file_type}")
    with open(file_path, "wb") as f:
        f.write(content)

    await knowledge_repository.create_document(
        doc_id=doc_id,
        user_id=user_id,
        file_name=filename,
        file_type=file_type,
        file_size=len(content),
    )

    asyncio.create_task(_process_document(doc_id, user_id, file_path, file_type))

    return KnowledgeUploadResponse(doc_id=doc_id, file_name=filename, status="processing")


async def _process_document(doc_id: str, user_id: int, file_path: str, file_type: str) -> None:
    """后台异步解析文档：加载分块 -> 向量化写入 -> 更新状态"""
    try:
        logger.info("kb_document_processing_started", doc_id=doc_id, user_id=user_id)

        chunks = document_loader_service.load_and_split(file_path, file_type)
        if not chunks:
            raise ValueError("文档解析后未提取到任何内容")

        chunk_count = vector_store_service.add_document_chunks(user_id, doc_id, chunks)

        await knowledge_repository.update_document_status(
            doc_id, "ready", chunk_count=chunk_count
        )
        logger.info(
            "kb_document_processing_completed", doc_id=doc_id, user_id=user_id, chunk_count=chunk_count
        )
    except Exception as e:
        logger.error("kb_document_processing_failed", doc_id=doc_id, user_id=user_id, error=str(e))
        await knowledge_repository.update_document_status(
            doc_id, "failed", error_message=str(e)[:500]
        )


async def list_documents(user_id: int) -> KnowledgeListResponse:
    rows = await knowledge_repository.list_documents(user_id)
    items = [KnowledgeDocumentItem.model_validate(row) for row in rows]
    return KnowledgeListResponse(items=items)


async def get_document_status(user_id: int, doc_id: str) -> KnowledgeStatusResponse:
    row = await knowledge_repository.get_document(doc_id, user_id)
    if row is None:
        raise KnowledgeBaseError("文档不存在")
    return KnowledgeStatusResponse(
        doc_id=row["doc_id"],
        file_name=row["file_name"],
        status=row["status"],
        chunk_count=row["chunk_count"],
        error_message=row.get("error_message"),
    )


async def delete_document(user_id: int, doc_id: str) -> None:
    """删除文档：级联清理向量、本地文件、数据库记录，任一步失败仅记录日志"""
    row = await knowledge_repository.get_document(doc_id, user_id)
    if row is None:
        raise KnowledgeBaseError("文档不存在")

    settings = get_settings()

    try:
        vector_store_service.delete_document_vectors(user_id, doc_id)
    except Exception as e:
        logger.warning("kb_document_vector_delete_failed", doc_id=doc_id, error=str(e))

    try:
        file_path = os.path.join(settings.kb_upload_dir, f"{doc_id}.{row['file_type']}")
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.warning("kb_document_file_delete_failed", doc_id=doc_id, error=str(e))

    try:
        await knowledge_repository.delete_document(doc_id, user_id)
    except Exception as e:
        logger.warning("kb_document_db_delete_failed", doc_id=doc_id, error=str(e))
