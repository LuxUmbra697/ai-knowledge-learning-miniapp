"""向量存储服务 - 基于 Chroma 的知识库向量检索"""

from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from typing import Optional

import structlog
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.core.config import get_settings

logger = structlog.get_logger()


def index_version() -> str:
    from app.services.document_loader_service import PARSER_VERSION
    settings = get_settings()
    configuration = [settings.dashscope_embedding_model, settings.dashscope_base_url,
                     settings.embedding_dimensions, settings.kb_chunk_size,
                     settings.kb_chunk_overlap, PARSER_VERSION, 'cosine-v1']
    return hashlib.sha256(json.dumps(configuration).encode()).hexdigest()[:16]


def scope_key(doc_id: str, revision: int, version: str) -> str:
    return f'{doc_id}:{revision}:{version}'


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
        dimensions=settings.embedding_dimensions,
        max_retries=0,
        request_timeout=settings.embedding_timeout_seconds,
        chunk_size=10,
    )


def get_user_vector_store(user_id: int, embeddings: Optional[Embeddings] = None, version: str | None = None):
    """获取指定用户的 Chroma 向量库实例（每用户一个 collection）"""
    from langchain_chroma import Chroma

    settings = get_settings()
    return Chroma(
        collection_name=f'kb_user_{user_id}' if version == 'legacy' else f"kb_u{user_id}_{version or index_version()}",
        embedding_function=embeddings or get_embeddings(),
        persist_directory=settings.chroma_persist_dir,
        collection_metadata={'hnsw:space': 'cosine'},
    )


def add_document_chunks(
    user_id: int,
    doc_id: str,
    chunks: list[Document],
    embeddings: Optional[Embeddings] = None,
    *, revision: int = 1, version: str | None = None,
) -> int:
    """将文档分块写入用户向量库，返回写入的分块数量"""
    if not chunks:
        return 0

    version = version or index_version()
    vector_store = get_user_vector_store(user_id, embeddings=embeddings, version=version)

    ids = []
    for index, chunk in enumerate(chunks):
        chunk_id = chunk.metadata.get('chunk_id') or hashlib.sha256(f'{index}:{chunk.page_content}'.encode()).hexdigest()[:32]
        chunk.metadata = {
            **chunk.metadata,
            "doc_id": doc_id,
            "user_id": user_id,
            'chunk_id': chunk_id,
            'revision': revision,
            'index_version': version,
            'scope_key': scope_key(doc_id, revision, version),
        }
        ids.append(f'{doc_id}:{revision}:{chunk_id}')

    # Bounded provider batches; deterministic IDs make a worker replay an upsert.
    for offset in range(0, len(chunks), 10):
        vector_store.add_documents(documents=chunks[offset:offset+10], ids=ids[offset:offset+10])
    logger.info("document_chunks_added", user_id=user_id, doc_id=doc_id, chunk_count=len(ids))
    return len(ids)


def delete_document_vectors(
    user_id: int,
    doc_id: str,
    embeddings: Optional[Embeddings] = None,
    *, revision: int | None = None, version: str | None = None,
) -> None:
    """从用户向量库中删除指定文档的所有向量"""
    vector_store = get_user_vector_store(user_id, embeddings=embeddings, version=version)
    where = {'doc_id': doc_id} if revision is None or version == 'legacy' else {'scope_key': scope_key(doc_id, revision, version or index_version())}
    vector_store.delete(where=where)
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


def search_scoped(user_id: int, scopes: list[str], query: str, k: int | None = None,
                  embeddings: Optional[Embeddings] = None) -> list[Document]:
    """Call only after SQL ownership/ready/version checks; filter before ANN search."""
    if not scopes:
        return []
    store = get_user_vector_store(user_id, embeddings=embeddings)
    return store.similarity_search(query, k=k or get_settings().kb_retrieve_candidates,
                                   filter={'scope_key': {'$in': scopes}})
