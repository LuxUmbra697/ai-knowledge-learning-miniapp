"""knowledge_service 单元测试"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.documents import Document

from app.core.exceptions import KnowledgeBaseError
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
async def test_handle_upload_rejects_when_quota_reached():
    settings = _patch_settings(kb_max_documents_per_user=2)
    with patch("app.services.knowledge_service.get_settings", return_value=settings), patch(
        "app.services.knowledge_service.knowledge_repository.count_documents",
        AsyncMock(return_value=2),
    ):
        with pytest.raises(KnowledgeBaseError, match="数量已达上限"):
            await knowledge_service.handle_upload(1, "sample.txt", b"content")


@pytest.mark.asyncio
async def test_handle_upload_success_saves_file_and_creates_record(tmp_path):
    settings = _patch_settings(kb_upload_dir=str(tmp_path))
    create_document_mock = AsyncMock()

    with patch("app.services.knowledge_service.get_settings", return_value=settings), patch(
        "app.services.knowledge_service.knowledge_repository.count_documents",
        AsyncMock(return_value=0),
    ), patch(
        "app.services.knowledge_service.knowledge_repository.create_document",
        create_document_mock,
    ), patch(
        "app.services.knowledge_service.asyncio.create_task"
    ) as mock_create_task:
        result = await knowledge_service.handle_upload(1, "sample.txt", b"hello world")

    assert result.status == "processing"
    assert result.file_name == "sample.txt"
    assert result.doc_id.startswith("doc_")

    create_document_mock.assert_called_once()
    mock_create_task.assert_called_once()
    # asyncio.create_task 被 mock 掉，需手动关闭协程避免 "never awaited" 警告
    mock_create_task.call_args[0][0].close()

    saved_file = tmp_path / f"{result.doc_id}.txt"
    assert saved_file.exists()
    assert saved_file.read_bytes() == b"hello world"


@pytest.mark.asyncio
async def test_process_document_success_updates_status_ready():
    fake_chunks = [Document(page_content="内容分块", metadata={})]
    update_status_mock = AsyncMock()

    with patch(
        "app.services.knowledge_service.document_loader_service.load_and_split",
        return_value=fake_chunks,
    ), patch(
        "app.services.knowledge_service.vector_store_service.add_document_chunks",
        return_value=1,
    ), patch(
        "app.services.knowledge_service.knowledge_repository.update_document_status",
        update_status_mock,
    ):
        await knowledge_service._process_document("doc_1", 1, "/tmp/doc_1.txt", "txt")

    update_status_mock.assert_called_once_with("doc_1", "ready", chunk_count=1)


@pytest.mark.asyncio
async def test_process_document_no_chunks_marks_failed():
    update_status_mock = AsyncMock()

    with patch(
        "app.services.knowledge_service.document_loader_service.load_and_split",
        return_value=[],
    ), patch(
        "app.services.knowledge_service.knowledge_repository.update_document_status",
        update_status_mock,
    ):
        await knowledge_service._process_document("doc_1", 1, "/tmp/doc_1.txt", "txt")

    args, kwargs = update_status_mock.call_args
    assert args[0] == "doc_1"
    assert args[1] == "failed"
    assert "error_message" in kwargs


@pytest.mark.asyncio
async def test_process_document_loader_exception_marks_failed():
    update_status_mock = AsyncMock()

    with patch(
        "app.services.knowledge_service.document_loader_service.load_and_split",
        side_effect=ValueError("解析失败"),
    ), patch(
        "app.services.knowledge_service.knowledge_repository.update_document_status",
        update_status_mock,
    ):
        await knowledge_service._process_document("doc_1", 1, "/tmp/doc_1.txt", "txt")

    args, kwargs = update_status_mock.call_args
    assert args[0] == "doc_1"
    assert args[1] == "failed"
    assert kwargs["error_message"] == "解析失败"


@pytest.mark.asyncio
async def test_get_document_status_raises_when_not_found():
    with patch(
        "app.services.knowledge_service.knowledge_repository.get_document",
        AsyncMock(return_value=None),
    ):
        with pytest.raises(KnowledgeBaseError, match="文档不存在"):
            await knowledge_service.get_document_status(1, "doc_missing")


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
        "app.services.knowledge_service.knowledge_repository.get_document",
        AsyncMock(return_value=None),
    ):
        with pytest.raises(KnowledgeBaseError, match="文档不存在"):
            await knowledge_service.delete_document(1, "doc_missing")


@pytest.mark.asyncio
async def test_delete_document_success_cascades(tmp_path):
    row = {"doc_id": "doc_1", "file_name": "a.txt", "file_type": "txt"}
    file_path = tmp_path / "doc_1.txt"
    file_path.write_text("content")

    settings = _patch_settings(kb_upload_dir=str(tmp_path))
    delete_vectors_mock = MagicMock()
    delete_db_mock = AsyncMock()

    with patch("app.services.knowledge_service.get_settings", return_value=settings), patch(
        "app.services.knowledge_service.knowledge_repository.get_document",
        AsyncMock(return_value=row),
    ), patch(
        "app.services.knowledge_service.vector_store_service.delete_document_vectors",
        delete_vectors_mock,
    ), patch(
        "app.services.knowledge_service.knowledge_repository.delete_document",
        delete_db_mock,
    ):
        await knowledge_service.delete_document(1, "doc_1")

    delete_vectors_mock.assert_called_once_with(1, "doc_1")
    delete_db_mock.assert_called_once_with("doc_1", 1)
    assert not file_path.exists()


@pytest.mark.asyncio
async def test_delete_document_tolerates_vector_delete_failure(tmp_path):
    row = {"doc_id": "doc_1", "file_name": "a.txt", "file_type": "txt"}
    file_path = tmp_path / "doc_1.txt"
    file_path.write_text("content")

    settings = _patch_settings(kb_upload_dir=str(tmp_path))
    delete_db_mock = AsyncMock()

    with patch("app.services.knowledge_service.get_settings", return_value=settings), patch(
        "app.services.knowledge_service.knowledge_repository.get_document",
        AsyncMock(return_value=row),
    ), patch(
        "app.services.knowledge_service.vector_store_service.delete_document_vectors",
        side_effect=RuntimeError("chroma unavailable"),
    ), patch(
        "app.services.knowledge_service.knowledge_repository.delete_document",
        delete_db_mock,
    ):
        # 不应抛出异常，即使向量删除失败
        await knowledge_service.delete_document(1, "doc_1")

    delete_db_mock.assert_called_once_with("doc_1", 1)
    assert not file_path.exists()
