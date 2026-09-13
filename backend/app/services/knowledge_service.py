"""知识库文档业务服务：上传、解析、状态查询、删除"""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
import re
import uuid

import structlog
from fastapi import HTTPException

from app.core.config import get_settings
from app.core.exceptions import KnowledgeBaseError
from app.models.knowledge import (
    KnowledgeDocumentItem,
    KnowledgeListResponse,
    KnowledgeStatusResponse,
    KnowledgeUploadResponse,
)
from app.repositories import knowledge_repository, rag_index_repository
from app.services import isolated_parser, vector_store_service

logger = structlog.get_logger()

SUPPORTED_EXTENSIONS = {"pdf", "docx", "md", "txt"}
_processing_slots = asyncio.Semaphore(1)
_background = set()


def _schedule(coroutine):
    task = asyncio.create_task(coroutine)
    _background.add(task)
    task.add_done_callback(_background.discard)


def _stored_path(storage_key):
    root = Path(get_settings().kb_upload_dir).resolve()
    path = (root / storage_key).resolve()
    if path.parent != root or not re.fullmatch(r'doc_[a-zA-Z0-9]+\.(pdf|docx|txt|md)', storage_key):
        raise KnowledgeBaseError('文档存储位置无效')
    return path


def _get_extension(filename: str) -> str:
    _, ext = os.path.splitext(filename)
    return ext.lstrip(".").lower()


async def handle_upload(user_id: int, filename: str, content: bytes) -> KnowledgeUploadResponse:
    """校验并保存上传的文档，后台异步解析处理"""
    settings = get_settings()

    if not content:
        raise KnowledgeBaseError('文件为空，请选择包含学习内容的文档')
    if len(filename) > 200 or '/' in filename or '\\' in filename or re.search(r'[\x00-\x1f]', filename):
        raise KnowledgeBaseError('文件名无效，请使用不含路径的文件名')

    file_type = _get_extension(filename)
    if file_type not in SUPPORTED_EXTENSIONS:
        raise KnowledgeBaseError(
            f"不支持的文件格式：{file_type or '未知'}，仅支持 PDF/Word/Markdown/文本文件"
        )

    max_size_bytes = settings.kb_max_file_size_mb * 1024 * 1024
    if len(content) > max_size_bytes:
        raise KnowledgeBaseError(f"文件大小超过限制（最大 {settings.kb_max_file_size_mb}MB）")
    if file_type in ('txt', 'md') and (b'\x00' in content or content.startswith(b'MZ')):
        raise KnowledgeBaseError('文件不是有效的文本资料')
    if file_type == 'pdf' and not content.startswith(b'%PDF-'):
        raise KnowledgeBaseError('PDF 文件签名无效')
    if file_type == 'docx' and not content.startswith(b'PK'):
        raise KnowledgeBaseError('DOCX 文件签名无效')

    doc_id = f"doc_{uuid.uuid4().hex}"
    version = vector_store_service.index_version()
    reservation = await rag_index_repository.reserve(doc_id, user_id, filename, file_type, len(content),
                                                     hashlib.sha256(content).hexdigest(), version,
                                                     settings.kb_max_documents_per_user)
    if reservation['duplicate']:
        return KnowledgeUploadResponse.model_validate(reservation)
    file_path = _stored_path(f'{doc_id}.{file_type}')
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(file_path.write_bytes, content)
    except OSError:
        await rag_index_repository.fail(doc_id, user_id, 1, version, '文件保存失败，请稍后重试上传')
        raise KnowledgeBaseError('文件保存失败，请稍后重试上传')
    _schedule(_process_document(doc_id, user_id, str(file_path), file_type, 1, version))
    return KnowledgeUploadResponse.model_validate(reservation)


async def _process_document(doc_id: str, user_id: int, file_path: str, file_type: str,
                            revision: int = 1, version: str | None = None, previous=None) -> None:
    """后台异步解析文档：加载分块 -> 向量化写入 -> 更新状态"""
    version = version or vector_store_service.index_version()
    async with _processing_slots:
        await _index_document(doc_id, user_id, file_path, file_type, revision, version, previous)


async def _index_document(doc_id, user_id, file_path, file_type, revision, version, previous):
    try:
        if not await rag_index_repository.is_current(doc_id, user_id, revision, version):
            return
        logger.info("kb_document_processing_started", doc_id=doc_id, user_id=user_id)

        chunks = await asyncio.to_thread(isolated_parser.parse_document, file_path, file_type)
        if not chunks:
            raise ValueError("文档解析后未提取到任何内容")
        if len(chunks) > 100:
            raise ValueError('文档超过单次索引的 100 个片段预算，请拆分为较小材料')
        if not await rag_index_repository.is_current(doc_id, user_id, revision, version):
            return

        chunk_count = await asyncio.to_thread(vector_store_service.add_document_chunks, user_id, doc_id, chunks,
                                              revision=revision, version=version)
        published = await rag_index_repository.publish(doc_id, user_id, revision, version, chunks)
        if not published:
            await asyncio.to_thread(vector_store_service.delete_document_vectors, user_id, doc_id,
                                    revision=revision, version=version)
            return
        if previous:
            try:
                await asyncio.to_thread(vector_store_service.delete_document_vectors, user_id, doc_id,
                                        revision=previous[0], version=previous[1])
            except Exception as error:
                logger.warning('kb_previous_revision_cleanup_failed', doc_id=doc_id, error_type=type(error).__name__)
        logger.info(
            "kb_document_processing_completed", doc_id=doc_id, user_id=user_id, chunk_count=chunk_count
        )
    except Exception as error:
        logger.error('kb_document_processing_failed', doc_id=doc_id, user_id=user_id, error_type=type(error).__name__)
        message = str(error)[:300] if isinstance(error, ValueError) else '索引服务暂时不可用，请稍后重试'
        await rag_index_repository.fail(doc_id, user_id, revision, version, message)


async def list_documents(user_id: int) -> KnowledgeListResponse:
    rows = await knowledge_repository.list_documents(user_id)
    items = [KnowledgeDocumentItem.model_validate({**row, 'needs_reindex': row.get('index_version') != vector_store_service.index_version()}) for row in rows]
    return KnowledgeListResponse(items=items)


async def get_document_status(user_id: int, doc_id: str) -> KnowledgeStatusResponse:
    row = await knowledge_repository.get_document(doc_id, user_id)
    if row is None:
        raise HTTPException(404, '文档不存在')
    return KnowledgeStatusResponse(
        doc_id=row["doc_id"],
        file_name=row["file_name"],
        status=row["status"],
        chunk_count=row["chunk_count"],
        error_message=row.get("error_message"),
        revision=row.get('revision'), index_version=row.get('index_version'),
        needs_reindex=row.get('index_version') != vector_store_service.index_version(),
    )


async def delete_document(user_id: int, doc_id: str) -> None:
    """Revoke SQL visibility first. Failed physical cleanup remains explicitly pending."""
    row = await rag_index_repository.tombstone(doc_id, user_id)
    try:
        await asyncio.to_thread(vector_store_service.delete_document_vectors, user_id, doc_id,
                                version=row['index_version'])
        await asyncio.to_thread(_stored_path(row['storage_key']).unlink, missing_ok=True)
        await rag_index_repository.cleanup_done(doc_id, user_id)
    except Exception as error:
        logger.warning('kb_cleanup_pending', doc_id=doc_id, error_type=type(error).__name__)


async def reindex_document(user_id: int, doc_id: str):
    meta = await rag_index_repository.begin_reindex(doc_id, user_id, vector_store_service.index_version())
    _schedule(_process_document(doc_id, user_id, str(_stored_path(meta['storage_key'])), meta['file_type'],
                               meta['revision'], meta['index_version'], meta['previous']))
    return {'doc_id': doc_id, 'status': 'processing', 'revision': meta['revision']}
