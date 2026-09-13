"""knowledge_service 单元测试"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.documents import Document

from app.core.exceptions import KnowledgeBaseError
from fastapi import HTTPException
from app.services import knowledge_service


def _patch_settings(**overrides):
    settings = MagicMock()
    settings.kb_max_file_size_mb = overrides.get("kb_max_file_size_mb", 10)
    settings.kb_max_documents_per_user = overrides.get("kb_max_documents_per_user", 10)
    settings.kb_upload_dir = overrides.get("kb_upload_dir", "./data/uploads")
    return settings


@pytest.mark.asyncio
async def test_handle_upload_rejects_unsupported_extension():
    with pytest.raises(KnowledgeBaseError, match="不支持的文件格式"):
        await knowledge_service.handle_upload(1, "sample.xlsx", b"content")


@pytest.mark.asyncio
async def test_handle_upload_rejects_oversized_file():
    settings = _patch_settings(kb_max_file_size_mb=1)
    with patch("app.services.knowledge_service.get_settings", return_value=settings):
        big_content = b"x" * (2 * 1024 * 1024)
        with pytest.raises(KnowledgeBaseError, match="文件大小超过限制"):
            await knowledge_service.handle_upload(1, "sample.txt", big_content)


@pytest.mark.asyncio
async def test_handle_upload_rejects_when_quota_reached(tmp_path):
    settings = _patch_settings(kb_max_documents_per_user=2, kb_upload_dir=str(tmp_path))
    with patch("app.services.knowledge_service.get_settings", return_value=settings), patch(
        "app.services.knowledge_service.rag_index_repository.reserve",
        AsyncMock(side_effect=KnowledgeBaseError('数量已达上限')),
    ):
        with pytest.raises(KnowledgeBaseError, match="数量已达上限"):
            await knowledge_service.handle_upload(1, "sample.txt", b"content")


@pytest.mark.asyncio
async def test_handle_upload_success_saves_file_and_creates_record(tmp_path):
    settings = _patch_settings(kb_upload_dir=str(tmp_path))
    async def reserved(doc_id, user_id, filename, *args):
        return dict(doc_id=doc_id, file_name=filename, status='processing', duplicate=False, task_id='job_test')
    create_document_mock = AsyncMock(side_effect=reserved)

    with patch("app.services.knowledge_service.get_settings", return_value=settings), patch(
        "app.services.knowledge_service.rag_index_repository.reserve",
        create_document_mock,
    ), patch(
        "app.services.knowledge_service.job_repository.activate", AsyncMock()
    ) as activate:
        result = await knowledge_service.handle_upload(1, "sample.txt", b"hello world")

    assert result.status == "processing"
    assert result.file_name == "sample.txt"
    assert result.doc_id.startswith("doc_")

    create_document_mock.assert_called_once()
    activate.assert_awaited_once_with('job_test', 1)

    saved_file = tmp_path / f"{result.doc_id}.txt"
    assert saved_file.exists()
    assert saved_file.read_bytes() == b"hello world"


@pytest.mark.asyncio
async def test_process_document_success_updates_status_ready():
    fake_chunks = [Document(page_content="内容分块", metadata={})]
    update_status_mock = AsyncMock()

    with patch(
        "app.services.knowledge_service.isolated_parser.parse_document",
        return_value=fake_chunks,
    ), patch(
        "app.services.knowledge_service.vector_store_service.add_document_chunks",
        return_value=1,
    ), patch(
        "app.services.knowledge_service.rag_index_repository.publish",
        update_status_mock,
    ), patch('app.services.knowledge_service.rag_index_repository.is_current', AsyncMock(return_value=True)):
        await knowledge_service._process_document("doc_1", 1, "/tmp/doc_1.txt", "txt")

    update_status_mock.assert_called_once_with('doc_1', 1, 1, knowledge_service.vector_store_service.index_version(), fake_chunks)


@pytest.mark.asyncio
async def test_process_document_no_chunks_marks_failed():
    update_status_mock = AsyncMock()

    with patch(
        "app.services.knowledge_service.isolated_parser.parse_document",
        return_value=[],
    ), patch(
        "app.services.knowledge_service.rag_index_repository.fail",
        update_status_mock,
    ), patch('app.services.knowledge_service.rag_index_repository.is_current', AsyncMock(return_value=True)):
        await knowledge_service._process_document("doc_1", 1, "/tmp/doc_1.txt", "txt")

    args, kwargs = update_status_mock.call_args
    assert args[0] == "doc_1"
    assert args[1:3] == (1, 1)
    assert '未提取' in args[4]


@pytest.mark.asyncio
async def test_process_document_loader_exception_marks_failed():
    update_status_mock = AsyncMock()

    with patch(
        "app.services.knowledge_service.isolated_parser.parse_document",
        side_effect=ValueError("解析失败"),
    ), patch(
        "app.services.knowledge_service.rag_index_repository.fail",
        update_status_mock,
    ), patch('app.services.knowledge_service.rag_index_repository.is_current', AsyncMock(return_value=True)):
        await knowledge_service._process_document("doc_1", 1, "/tmp/doc_1.txt", "txt")

    args, kwargs = update_status_mock.call_args
    assert args[0] == "doc_1"
    assert args[1:3] == (1, 1)
    assert args[4] == "解析失败"


@pytest.mark.asyncio
async def test_get_document_status_raises_when_not_found():
    with patch(
        "app.services.knowledge_service.knowledge_repository.get_document",
        AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as error:
            await knowledge_service.get_document_status(1, "doc_missing")
        assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_get_document_status_returns_data_when_found():
    row = {
        "doc_id": "doc_1",
        "file_name": "a.txt",
        "status": "ready",
        "chunk_count": 3,
        "error_message": None,
    }
    with patch(
        "app.services.knowledge_service.knowledge_repository.get_document",
        AsyncMock(return_value=row),
    ):
        result = await knowledge_service.get_document_status(1, "doc_1")

    assert result.doc_id == "doc_1"
    assert result.status == "ready"
    assert result.chunk_count == 3


@pytest.mark.asyncio
async def test_delete_document_raises_when_not_found():
    with patch(
        "app.services.knowledge_service.rag_index_repository.tombstone",
        AsyncMock(side_effect=HTTPException(404, '文档不存在')),
    ):
        with pytest.raises(HTTPException) as error:
            await knowledge_service.delete_document(1, "doc_missing")
        assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_document_success_cascades(tmp_path):
    row = {'index_version': 'v1', 'storage_key': 'doc_1.txt'}
    file_path = tmp_path / "doc_1.txt"
    file_path.write_text("content")

    settings = _patch_settings(kb_upload_dir=str(tmp_path))
    delete_vectors_mock = MagicMock()
    delete_db_mock = AsyncMock()

    with patch("app.services.knowledge_service.get_settings", return_value=settings), patch(
        "app.services.knowledge_service.rag_index_repository.tombstone",
        AsyncMock(return_value=row),
    ), patch(
        "app.services.knowledge_service.vector_store_service.delete_document_vectors",
        delete_vectors_mock,
    ), patch(
        "app.services.knowledge_service.rag_index_repository.cleanup_done",
        delete_db_mock,
    ):
        await knowledge_service.delete_document(1, "doc_1")

    # Deletion must cover all model/index versions, including interrupted rebuilds.
    delete_vectors_mock.assert_called_once_with(1, 'doc_1')
    delete_db_mock.assert_called_once_with("doc_1", 1)
    assert not file_path.exists()


@pytest.mark.asyncio
async def test_delete_document_tolerates_vector_delete_failure(tmp_path):
    row = {'index_version': 'v1', 'storage_key': 'doc_1.txt'}
    file_path = tmp_path / "doc_1.txt"
    file_path.write_text("content")

    settings = _patch_settings(kb_upload_dir=str(tmp_path))
    delete_db_mock = AsyncMock()

    with patch("app.services.knowledge_service.get_settings", return_value=settings), patch(
        "app.services.knowledge_service.rag_index_repository.tombstone",
        AsyncMock(return_value=row),
    ), patch(
        "app.services.knowledge_service.vector_store_service.delete_document_vectors",
        side_effect=RuntimeError("chroma unavailable"),
    ), patch(
        "app.services.knowledge_service.rag_index_repository.cleanup_done",
        delete_db_mock,
    ):
        # 不应抛出异常，即使向量删除失败
        await knowledge_service.delete_document(1, "doc_1")

    delete_db_mock.assert_not_called()
    assert file_path.exists()  # Retained for the pending cleanup retry, never searchable.


@pytest.mark.asyncio
async def test_stale_index_never_publishes_and_cleans_its_revision():
    with patch.object(knowledge_service.rag_index_repository, 'is_current', AsyncMock(return_value=True)), \
         patch.object(knowledge_service.isolated_parser, 'parse_document', return_value=[Document(page_content='text')]), \
         patch.object(knowledge_service.vector_store_service, 'add_document_chunks', return_value=1), \
         patch.object(knowledge_service.rag_index_repository, 'publish', AsyncMock(return_value=False)), \
         patch.object(knowledge_service.vector_store_service, 'delete_document_vectors') as cleanup:
        await knowledge_service._process_document('doc_1', 1, 'unused', 'txt', 2, 'v1')
    cleanup.assert_called_once_with(1, 'doc_1', revision=2, version='v1')


@pytest.mark.asyncio
async def test_duplicate_does_not_schedule_or_write(tmp_path):
    row = dict(doc_id='doc_existing', file_name='old.txt', status='ready', duplicate=True)
    with patch.object(knowledge_service, 'get_settings', return_value=_patch_settings(kb_upload_dir=str(tmp_path))), \
         patch.object(knowledge_service.rag_index_repository, 'reserve', AsyncMock(return_value=row)), \
         patch.object(knowledge_service.job_repository, 'activate', AsyncMock()) as schedule:
        result = await knowledge_service.handle_upload(1, 'copy.txt', b'existing')
    assert result.duplicate and result.doc_id == 'doc_existing'
    schedule.assert_not_called()
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_expired_index_worker_cannot_mark_new_owner_work_failed():
    from app.repositories.job_repository import TaskLeaseLost
    context = MagicMock()
    context.checkpoints = {}
    context.checkpoint = AsyncMock(side_effect=TaskLeaseLost())
    with patch.object(knowledge_service.rag_index_repository, 'is_current', AsyncMock(return_value=True)), \
         patch.object(knowledge_service.rag_index_repository, 'fail', AsyncMock()) as fail:
        with pytest.raises(TaskLeaseLost):
            await knowledge_service._process_document('doc_a', 1, 'unused', 'txt', 1, 'v1', context=context)
    fail.assert_not_called()
