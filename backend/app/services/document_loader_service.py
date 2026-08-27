"""文档解析服务 - 加载不同格式文档并分块"""

from __future__ import annotations

from typing import Optional

import structlog
from langchain_core.documents import Document

from app.core.config import get_settings

logger = structlog.get_logger()

SUPPORTED_FILE_TYPES = {"pdf", "docx", "md", "txt"}


def _load_documents(file_path: str, file_type: str) -> list[Document]:
    """按文件类型分发到对应的 LangChain Loader"""
    file_type = file_type.lower().lstrip(".")

    if file_type == "pdf":
        from langchain_community.document_loaders import PyPDFLoader

        return PyPDFLoader(file_path).load()

    if file_type == "docx":
        from langchain_community.document_loaders import Docx2txtLoader

        return Docx2txtLoader(file_path).load()

    if file_type in ("md", "txt"):
        from langchain_community.document_loaders import TextLoader

        return TextLoader(file_path, encoding="utf-8").load()

    raise ValueError(f"不支持的文件格式: {file_type}")


def load_and_split(
    file_path: str,
    file_type: str,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> list[Document]:
    """加载文档并分块，返回分块后的 Document 列表"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    settings = get_settings()
    chunk_size = chunk_size or settings.kb_chunk_size
    chunk_overlap = chunk_overlap or settings.kb_chunk_overlap

    docs = _load_documents(file_path, file_type)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    splits = splitter.split_documents(docs)

    logger.info(
        "document_loaded_and_split",
        file_type=file_type,
        raw_doc_count=len(docs),
        chunk_count=len(splits),
    )
    return splits
