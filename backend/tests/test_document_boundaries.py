import hashlib
import zipfile
from unittest.mock import patch

import pytest
from pypdf import PdfWriter

from app.services.document_loader_service import load_and_split


@pytest.mark.parametrize('content', [b'', b'   \n\t', b'\x00\x01\x02', b'\xff\xfe\xfa'])
def test_empty_binary_or_invalid_text_is_rejected(tmp_path, content):
    file = tmp_path / 'note.txt'
    file.write_bytes(content)
    with pytest.raises(ValueError):
        load_and_split(str(file), 'txt')


def test_markdown_chapters_and_stable_hashes(tmp_path):
    file = tmp_path / 'lesson.md'
    file.write_text('# 第一章\n\n数组保存有序元素。\n\n## 字典\n\n字典通过键定位值。', encoding='utf-8-sig')
    first = load_and_split(str(file), 'md', chunk_size=80, chunk_overlap=10)
    second = load_and_split(str(file), 'md', chunk_size=80, chunk_overlap=10)
    assert {chunk.metadata['section'] for chunk in first} == {'第一章', '第一章 / 字典'}
    assert [chunk.metadata['chunk_id'] for chunk in first] == [chunk.metadata['chunk_id'] for chunk in second]
    assert all(chunk.metadata['content_hash'] == hashlib.sha256(chunk.page_content.encode()).hexdigest() for chunk in first)
    assert all('source' not in chunk.metadata for chunk in first)


@pytest.mark.parametrize('encrypted', [False, True])
def test_blank_scanned_or_encrypted_pdf_explains_limit(tmp_path, encrypted):
    file = tmp_path / 'scan.pdf'
    writer = PdfWriter(); writer.add_blank_page(300, 300)
    if encrypted:
        writer.encrypt('test-only-password')
    writer.write(file)
    with pytest.raises(ValueError, match='加密|扫描|文本'):
        load_and_split(str(file), 'pdf')


def test_damaged_pdf_is_rejected(tmp_path):
    file = tmp_path / 'broken.pdf'; file.write_bytes(b'%PDF-broken')
    with pytest.raises(ValueError, match='损坏|PDF'):
        load_and_split(str(file), 'pdf')


def test_pdf_page_limit(tmp_path):
    from app.core.config import Settings
    file = tmp_path / 'too-many.pdf'
    writer = PdfWriter()
    for _ in range(3): writer.add_blank_page(300, 300)
    writer.write(file)
    settings = Settings(_env_file=None)
    settings.kb_max_pdf_pages = 2
    with patch('app.services.document_loader_service.get_settings', return_value=settings):
        with pytest.raises(ValueError, match='页数'):
            load_and_split(str(file), 'pdf')


def test_docx_heading_and_paragraphs(tmp_path):
    file = tmp_path / 'notes.docx'
    xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>数据结构</w:t></w:r></w:p><w:p><w:r><w:t>栈遵循后进先出原则。</w:t></w:r></w:p></w:body></w:document>'
    with zipfile.ZipFile(file, 'w') as archive: archive.writestr('word/document.xml', xml)
    chunks = load_and_split(str(file), 'docx')
    assert chunks[0].metadata['section'] == '数据结构'
    assert '后进先出' in chunks[0].page_content


def test_docx_zip_bomb_and_traversal_members_rejected(tmp_path):
    file = tmp_path / 'unsafe.docx'
    for member, data in [('word/document.xml', b'x' * 1_000_000), ('../../escape.xml', b'data')]:
        with zipfile.ZipFile(file, 'w', compression=zipfile.ZIP_DEFLATED) as archive: archive.writestr(member, data)
        with pytest.raises(ValueError, match='压缩|路径|DOCX'):
            load_and_split(str(file), 'docx')


def test_isolated_parser_real_process(tmp_path):
    from app.services.isolated_parser import parse_document
    file = tmp_path / 'isolated.md'
    file.write_text('# 来源\n\n独立解析进程保留章节。', encoding='utf-8')
    chunks = parse_document(str(file), 'md')
    assert chunks[0].metadata['section'] == '来源'


def test_isolated_parser_timeout_is_friendly():
    import subprocess
    from app.services.isolated_parser import parse_document
    with patch('app.services.isolated_parser.subprocess.run', side_effect=subprocess.TimeoutExpired('parser', 1)):
        with pytest.raises(ValueError, match='超时'):
            parse_document('ignored.md', 'md')
