"""document_loader_service 单元测试"""

import zipfile

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


def test_load_and_split_pdf_preserves_real_page_text(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    file_path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(300, 300)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject(); stream.set_data(b'BT /F1 12 Tf 20 200 Td (Evidence stays on page one.) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    writer.write(file_path)
    chunks = document_loader_service.load_and_split(str(file_path), "pdf")
    assert len(chunks) == 1
    assert 'Evidence stays' in chunks[0].page_content
    assert chunks[0].metadata['page'] == 1


def test_load_and_split_docx_preserves_real_paragraph_text(tmp_path):
    file_path = tmp_path / "sample.docx"
    with zipfile.ZipFile(file_path, 'w') as archive:
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Word 文档内容</w:t></w:r></w:p></w:body></w:document>')
    chunks = document_loader_service.load_and_split(str(file_path), "docx")
    assert len(chunks) == 1
    assert chunks[0].page_content == 'Word 文档内容'
    assert chunks[0].metadata['chunk_id']


def test_load_and_split_unsupported_format_raises(tmp_path):
    file_path = tmp_path / "sample.xlsx"
    file_path.write_bytes(b"fake content")

    with pytest.raises(ValueError, match="不支持的文件格式"):
        document_loader_service.load_and_split(str(file_path), "xlsx")
