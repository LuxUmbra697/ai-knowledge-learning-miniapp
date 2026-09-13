from unittest.mock import AsyncMock, patch
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.auth import create_token
from app.models.knowledge import KnowledgeUploadResponse


@pytest.mark.asyncio
async def test_declared_oversized_upload_is_refused_before_parser():
    mocked = AsyncMock(return_value=KnowledgeUploadResponse(doc_id='doc_test', file_name='a.txt', status='processing'))
    with patch('app.services.knowledge_service.handle_upload', mocked):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post('/api/v1/knowledge/documents', files={'file': ('a.txt', b'hello')},
                headers={'Authorization': 'Bearer ' + create_token(1, 'test'), 'Content-Length': str(20 * 1024 * 1024)})
    assert response.status_code == 413
    mocked.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('filename,content', [('empty.txt', b''), ('../outside.txt', b'data'), ('evil.exe.txt', b'MZ\x00binary')])
async def test_invalid_uploads_never_schedule_work(filename, content, tmp_path):
    from app.services.knowledge_service import handle_upload
    from app.core.exceptions import KnowledgeBaseError
    from app.core.config import Settings
    settings = Settings(_env_file=None, kb_upload_dir=str(tmp_path))
    with patch('app.services.knowledge_service.get_settings', return_value=settings), \
         patch('app.services.knowledge_service.knowledge_repository.count_documents', AsyncMock(return_value=0)), \
         patch('app.services.knowledge_service.knowledge_repository.create_document', AsyncMock()), \
         patch('app.services.knowledge_service.asyncio.create_task') as schedule:
        with pytest.raises(KnowledgeBaseError):
            await handle_upload(1, filename, content)
        schedule.assert_not_called()


@pytest.mark.asyncio
async def test_chunked_stream_is_bounded_without_content_length():
    from app.core.upload_limits import UploadLimitsMiddleware
    from app.core.config import Settings
    called = AsyncMock()
    receive = AsyncMock(side_effect=[{'type': 'http.request', 'body': b'a' * 700000, 'more_body': True},
                                    {'type': 'http.request', 'body': b'b' * 700000, 'more_body': False}])
    send = AsyncMock()
    with patch('app.core.upload_limits.get_settings', return_value=Settings(_env_file=None, kb_max_file_size_mb=1)):
        middleware = UploadLimitsMiddleware(called)
        await middleware({'type': 'http', 'method': 'POST', 'path': '/api/v1/knowledge/documents', 'headers': []}, receive, send)
    assert send.call_args_list[0].args[0]['status'] == 413
    called.assert_not_called()
    assert middleware.slots._value == 2


@pytest.mark.asyncio
async def test_upload_disconnect_releases_capacity():
    from app.core.upload_limits import UploadLimitsMiddleware
    called = AsyncMock(); send = AsyncMock()
    middleware = UploadLimitsMiddleware(called)
    await middleware({'type': 'http', 'method': 'POST', 'path': '/api/v1/knowledge/documents', 'headers': []},
                     AsyncMock(return_value={'type': 'http.disconnect'}), send)
    called.assert_not_called(); send.assert_not_called()
    assert middleware.slots._value == 2
