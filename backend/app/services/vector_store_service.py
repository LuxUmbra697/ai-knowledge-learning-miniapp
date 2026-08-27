"""向量存储服务 - 基于 Chroma 的知识库向量检索"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

import structlog
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.core.config import get_settings

logger = structlog.get_logger()


@lru_cache
def get_embeddings() -> Embeddings:
    """获取百炼 text-embedding-v4 Embedding 实例（OpenAI 兼容模式）

    check_embedding_ctx_length=False：禁用 langchain_openai 默认的 tiktoken 分词/截断行为。
    该行为会把文本先编码成 token id 数组再发送，而非 OpenAI 官方模型的服务端（如 DashScope
    兼容模式端点）无法识别 token id 数组，会报 "contents is neither str nor list of str" 错误。
    """
    from langchain_openai import OpenAIEmbeddings

    settings = get_settings()
    return OpenAIEmbeddings(
        model=settings.dashscope_embedding_model,
        base_url=settings.dashscope_base_url,
        api_key=settings.dashscope_api_key,
        check_embedding_ctx_length=False,
    )


def get_user_vector_store(user_id: int, embeddings: Optional[Embeddings] = None):
    """获取指定用户的 Chroma 向量库实例（每用户一个 collection）"""
    from langchain_chroma import Chroma

    settings = get_settings()
    return Chroma(
        collection_name=f"kb_user_{user_id}",
        embedding_function=embeddings or get_embeddings(),
        persist_directory=settings.chroma_persist_dir,
    )


def add_document_chunks(
    user_id: int,
    doc_id: str,
    chunks: list[Document],
    embeddings: Optional[Embeddings] = None,
) -> int:
    """将文档分块写入用户向量库，返回写入的分块数量"""
    if not chunks:
        return 0

    vector_store = get_user_vector_store(user_id, embeddings=embeddings)

    for chunk in chunks:
        chunk.metadata = {
            **chunk.metadata,
            "doc_id": doc_id,
            "user_id": user_id,
        }

    ids = vector_store.add_documents(documents=chunks)
    logger.info("document_chunks_added", user_id=user_id, doc_id=doc_id, chunk_count=len(ids))
    return len(ids)


def delete_document_vectors(
    user_id: int,
    doc_id: str,
    embeddings: Optional[Embeddings] = None,
) -> None:
    """从用户向量库中删除指定文档的所有向量"""
    vector_store = get_user_vector_store(user_id, embeddings=embeddings)
    vector_store.delete(where={"doc_id": doc_id})
    logger.info("document_vectors_deleted", user_id=user_id, doc_id=doc_id)


def similarity_search(
    user_id: int,
    doc_id: str,
    query: str,
    k: Optional[int] = None,
    embeddings: Optional[Embeddings] = None,
) -> list[Document]:
    """在用户向量库中检索指定文档的相关分块"""
    settings = get_settings()
    k = k or settings.kb_retrieve_top_k

    vector_store = get_user_vector_store(user_id, embeddings=embeddings)
    return vector_store.similarity_search(query, k=k, filter={"doc_id": doc_id})
