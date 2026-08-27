"""document_loader_service 单元测试"""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from app.services import document_loader_service


@pytest.fixture
def sample_text_content():
    # 生成足够长的文本，确保会被分成多个 chunk
    paragraph = "这是一段用于测试的知识库文档内容。" * 20
    return "\n\n".join([paragraph] * 5)


def test_load_and_split_txt(tmp_path, sample_text_content):
    file_path = tmp_path / "sample.txt"
    file_path.write_text(sample_text_content, encoding="utf-8")

    chunks = document_loader_service.load_and_split(str(file_path), "txt")

    assert len(chunks) > 1
    assert all(isinstance(c, Document) for c in chunks)
    assert all(c.page_content.strip() for c in chunks)


def test_load_and_split_md(tmp_path, sample_text_content):
    file_path = tmp_path / "sample.md"
    file_path.write_text(f"# 标题\n\n{sample_text_content}", encoding="utf-8")

    chunks = document_loader_service.load_and_split(str(file_path), "md")

    assert len(chunks) > 1


def test_load_and_split_respects_chunk_size(tmp_path):
    content = "字" * 5000
    file_path = tmp_path / "big.txt"
    file_path.write_text(content, encoding="utf-8")

    chunks = document_loader_service.load_and_split(
        str(file_path), "txt", chunk_size=500, chunk_overlap=50
    )

    assert len(chunks) >= 5
    for chunk in chunks:
        assert len(chunk.page_content) <= 500


def test_load_and_split_pdf_dispatches_to_pypdf_loader(tmp_path):
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-1.4 fake content")

    fake_docs = [Document(page_content="PDF 页面内容 " * 100, metadata={"page": 0})]
    mock_loader_instance = MagicMock()
    mock_loader_instance.load.return_value = fake_docs

    with patch(
        "langchain_community.document_loaders.PyPDFLoader",
        return_value=mock_loader_instance,
    ) as mock_loader_cls:
        chunks = document_loader_service.load_and_split(str(file_path), "pdf")

        mock_loader_cls.assert_called_once_with(str(file_path))
        assert len(chunks) >= 1


def test_load_and_split_docx_dispatches_to_docx2txt_loader(tmp_path):
    file_path = tmp_path / "sample.docx"
    file_path.write_bytes(b"fake docx content")

    fake_docs = [Document(page_content="Word 文档内容 " * 100, metadata={})]
    mock_loader_instance = MagicMock()
    mock_loader_instance.load.return_value = fake_docs

    with patch(
        "langchain_community.document_loaders.Docx2txtLoader",
        return_value=mock_loader_instance,
    ) as mock_loader_cls:
        chunks = document_loader_service.load_and_split(str(file_path), "docx")

        mock_loader_cls.assert_called_once_with(str(file_path))
        assert len(chunks) >= 1


def test_load_and_split_unsupported_format_raises(tmp_path):
    file_path = tmp_path / "sample.xlsx"
    file_path.write_bytes(b"fake content")

    with pytest.raises(ValueError, match="不支持的文件格式"):
        document_loader_service.load_and_split(str(file_path), "xlsx")
