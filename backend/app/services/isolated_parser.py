"""Run untrusted PDF/XML parsing in a short-lived, killable process."""
import json
import os
from pathlib import Path
import subprocess
import sys

from langchain_core.documents import Document
from app.core.config import get_settings

LIMIT_KEYS = ('kb_max_pdf_pages', 'kb_max_text_chars', 'kb_parse_timeout_seconds',
              'kb_max_uncompressed_mb', 'kb_max_file_size_mb', 'kb_chunk_size', 'kb_chunk_overlap')


def parse_document(file_path: str, file_type: str) -> list[Document]:
    settings = get_settings()
    payload = {'path': file_path, 'type': file_type, 'limits': {key: getattr(settings, key) for key in LIMIT_KEYS}}
    environment = {key: value for key, value in os.environ.items() if key.upper() in ('PATH', 'SYSTEMROOT', 'TEMP', 'TMP', 'WINDIR')}
    environment.update(AI_LEARN_ENV_FILE='', PYTHONUTF8='1')
    try:
        result = subprocess.run([sys.executable, '-m', 'app.services.isolated_parser'],
            input=json.dumps(payload), capture_output=True, text=True, encoding='utf-8',
            timeout=settings.kb_parse_timeout_seconds, check=False,
            cwd=Path(__file__).resolve().parents[2], env=environment)
    except subprocess.TimeoutExpired:
        raise ValueError('文档解析超时，请拆分后重试') from None
    if result.returncode or len(result.stdout) > 8_000_000:
        raise ValueError('文档解析未能完成，文件可能过于复杂或损坏')
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise ValueError('文档解析返回无效结果') from None
    if data.get('error'):
        raise ValueError(data['error'])
    return [Document(page_content=item['text'], metadata=item['metadata']) for item in data['chunks']]


def worker():
    if sys.platform != 'win32':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024, 384 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    payload = json.loads(sys.stdin.read(16384))
    for key in LIMIT_KEYS:
        os.environ[key.upper()] = str(payload['limits'][key])
    from app.services.document_loader_service import load_and_split
    try:
        chunks = load_and_split(payload['path'], payload['type'])
        data = {'chunks': [{'text': chunk.page_content, 'metadata': chunk.metadata} for chunk in chunks]}
    except ValueError as error:
        data = {'error': str(error)}
    except Exception:
        data = {'error': '文档解析失败，请重新导出或拆分文件'}
    sys.stdout.write(json.dumps(data, ensure_ascii=True))


if __name__ == '__main__':
    worker()
