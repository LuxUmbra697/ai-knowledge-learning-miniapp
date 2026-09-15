"""Bounded text extraction with one-based page/section and stable chunk metadata."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path, PurePosixPath
import re
import time
import zipfile

from langchain_core.documents import Document
from app.core.config import get_settings

SUPPORTED_FILE_TYPES = {'pdf', 'docx', 'md', 'txt'}
PARSER_VERSION = 'layout-v1'


def _section_documents(text: str, markdown: bool = False) -> list[Document]:
    documents, paragraphs, headings = [], [], []
    fence = False

    def flush():
        content = '\n'.join(paragraphs).strip()
        if content:
            documents.append(Document(page_content=content, metadata={'section': ' / '.join(headings), 'page': 0}))
        paragraphs.clear()

    for line in text.splitlines():
        if line.lstrip().startswith(('```', '~~~')):
            fence = not fence
        heading = re.match(r'^(#{1,6})\s+(.+?)\s*#*$', line) if markdown and not fence else None
        if heading:
            flush()
            depth = len(heading[1])
            headings = headings[:depth - 1] + [heading[2]]
        paragraphs.append(line)
    flush()
    return documents


def _load_documents(file_path: str, file_type: str) -> list[Document]:
    from pypdf import PdfReader
    from defusedxml.ElementTree import fromstring

    settings = get_settings()
    file_type = file_type.lower().lstrip('.')
    if file_type not in SUPPORTED_FILE_TYPES:
        raise ValueError(f'不支持的文件格式: {file_type}')
    path = Path(file_path)
    size = path.stat().st_size
    if not size:
        raise ValueError('文件为空，请选择包含学习内容的文档')
    if size > settings.kb_max_file_size_mb * 1024 * 1024:
        raise ValueError('文件大小超过解析限制')
    content = path.read_bytes()
    deadline = time.monotonic() + settings.kb_parse_timeout_seconds
    if file_type in ('txt', 'md'):
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise ValueError('文本编码无法识别，请另存为 UTF-8 后上传') from None
        if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', text):
            raise ValueError('文件包含二进制控制字符，不能作为文本解析')
        docs = _section_documents(text, markdown=file_type == 'md')
    elif file_type == 'pdf':
        if not content.startswith(b'%PDF-'):
            raise ValueError('PDF 文件签名不正确或文件损坏')
        try:
            reader = PdfReader(io.BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise ValueError('PDF 已加密，请解密后重新上传')
            if len(reader.pages) > settings.kb_max_pdf_pages:
                raise ValueError(f'PDF 页数超过限制（最多 {settings.kb_max_pdf_pages} 页）')
            docs = []
            chars = 0
            for number, page in enumerate(reader.pages, 1):
                if time.monotonic() > deadline:
                    raise ValueError('PDF 解析超时，请拆分文档后重试')
                stream = page.get_contents()
                if stream and len(stream.get_data()) > settings.kb_max_uncompressed_mb * 1024 * 1024:
                    raise ValueError('PDF 页面解压内容过大，请拆分文档')
                text = page.extract_text() or ''
                chars += len(text)
                if chars > settings.kb_max_text_chars:
                    raise ValueError('文档文本量超过限制，请拆分后上传')
                if text.strip():
                    docs.append(Document(page_content=text, metadata={'page': number, 'section': f'第 {number} 页'}))
            if not docs:
                raise ValueError('PDF 未提取到文本，可能是扫描件；当前未启用 OCR')
        except ValueError:
            raise
        except Exception:
            raise ValueError('PDF 文件损坏或无法解析，请重新导出文件') from None
    else:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                entries = archive.infolist()
                if len(entries) > 2000 or sum(entry.file_size for entry in entries) > settings.kb_max_uncompressed_mb * 1024 * 1024:
                    raise ValueError('DOCX 解压大小超过限制')
                for entry in entries:
                    if '..' in PurePosixPath(entry.filename).parts or entry.filename.startswith(('/', '\\')) or '\\' in entry.filename:
                        raise ValueError('DOCX 压缩包包含危险路径')
                    if entry.file_size > 100000 and entry.file_size / max(entry.compress_size, 1) > 100:
                        raise ValueError('DOCX 压缩率异常，请重新导出文档')
                    if 'vbaproject' in entry.filename.lower():
                        raise ValueError('不支持含宏的 DOCX 文档')
                if 'word/document.xml' not in archive.namelist():
                    raise ValueError('DOCX 缺少正文，文件可能已损坏')
                root = fromstring(archive.read('word/document.xml'))
                namespace = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                lines = []
                for paragraph in root.findall('.//w:p', namespace):
                    if time.monotonic() > deadline:
                        raise ValueError('DOCX 解析超时，请拆分后上传')
                    text = ''.join(element.text or '' for element in paragraph.findall('.//w:t', namespace))
                    style = paragraph.find('./w:pPr/w:pStyle', namespace)
                    value = style.get('{' + namespace['w'] + '}val', '') if style is not None else ''
                    heading = re.match(r'(?:Heading|标题)([1-6])$', value, re.I)
                    lines.append(('#' * int(heading[1]) + ' ' if heading else '') + text)
                docs = _section_documents('\n\n'.join(lines), markdown=True)
        except ValueError:
            raise
        except Exception:
            raise ValueError('DOCX 文件损坏或正文格式无法解析') from None
    if not docs:
        raise ValueError('文档没有可提取的文本内容')
    if sum(len(doc.page_content) for doc in docs) > settings.kb_max_text_chars:
        raise ValueError('文档文本量超过限制，请拆分后上传')
    return docs


def load_and_split(file_path: str, file_type: str, chunk_size: int | None = None, chunk_overlap: int | None = None) -> list[Document]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    settings = get_settings()
    size = chunk_size if chunk_size is not None else settings.kb_chunk_size
    overlap = chunk_overlap if chunk_overlap is not None else settings.kb_chunk_overlap
    if size < 32 or not 0 <= overlap < size:
        raise ValueError('分块长度或重叠参数不合法')
    docs = _load_documents(file_path, file_type)
    source_hash = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
    splitter = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap, add_start_index=True,
        separators=['\n\n', '\n', '。', '！', '？', '；', '. ', ' ', ''])
    chunks = splitter.split_documents(docs)
    if len(chunks) > 2000:
        raise ValueError('文档分块过多，请拆分文档')
    for index, chunk in enumerate(chunks):
        content_hash = hashlib.sha256(chunk.page_content.encode()).hexdigest()
        chunk.metadata = {**chunk.metadata, 'content_hash': content_hash, 'document_hash': source_hash,
            'parser_version': PARSER_VERSION, 'chunk_index': index,
            'chunk_id': hashlib.sha256(f'{source_hash}:{PARSER_VERSION}:{size}:{overlap}:{index}:{content_hash}'.encode()).hexdigest()[:32]}
    return chunks
