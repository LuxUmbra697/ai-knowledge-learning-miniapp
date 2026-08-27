"""vector_store_service 单元测试（使用确定性伪 Embedding + 真实 Chroma 临时目录）"""

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding

from app.services import vector_store_service


@pytest.fixture
def fake_embeddings():
    return DeterministicFakeEmbedding(size=64)


@pytest.fixture
def persist_dir(tmp_path, monkeypatch):
    dir_path = tmp_path / "chroma"
    monkeypatch.setattr(
        vector_store_service.get_settings(), "chroma_persist_dir", str(dir_path)
    )
    return str(dir_path)


def _make_chunks(text_variants):
    return [Document(page_content=text, metadata={}) for text in text_variants]


def test_add_document_chunks_returns_count(persist_dir, fake_embeddings):
    chunks = _make_chunks(["苹果是一种水果", "香蕉是一种水果"])

    count = vector_store_service.add_document_chunks(
        user_id=1, doc_id="doc-a", chunks=chunks, embeddings=fake_embeddings
    )

    assert count == 2


def test_add_document_chunks_empty_list_returns_zero(persist_dir, fake_embeddings):
    count = vector_store_service.add_document_chunks(
        user_id=1, doc_id="doc-a", chunks=[], embeddings=fake_embeddings
    )
    assert count == 0


def test_similarity_search_filters_by_doc_id(persist_dir, fake_embeddings):
    chunks_a = _make_chunks(["文档A讲的是猫", "文档A讲的是狗"])
    chunks_b = _make_chunks(["文档B讲的是汽车", "文档B讲的是飞机"])

    vector_store_service.add_document_chunks(
        user_id=1, doc_id="doc-a", chunks=chunks_a, embeddings=fake_embeddings
    )
    vector_store_service.add_document_chunks(
        user_id=1, doc_id="doc-b", chunks=chunks_b, embeddings=fake_embeddings
    )

    results = vector_store_service.similarity_search(
        user_id=1, doc_id="doc-a", query="猫", k=5, embeddings=fake_embeddings
    )

    assert len(results) == 2
    assert all(r.metadata["doc_id"] == "doc-a" for r in results)


def test_similarity_search_isolates_users(persist_dir, fake_embeddings):
    chunks_user1 = _make_chunks(["用户1的私有内容"])
    chunks_user2 = _make_chunks(["用户2的私有内容"])

    vector_store_service.add_document_chunks(
        user_id=1, doc_id="doc-shared-id", chunks=chunks_user1, embeddings=fake_embeddings
    )
    vector_store_service.add_document_chunks(
        user_id=2, doc_id="doc-shared-id", chunks=chunks_user2, embeddings=fake_embeddings
    )

    results_user1 = vector_store_service.similarity_search(
        user_id=1, doc_id="doc-shared-id", query="内容", k=5, embeddings=fake_embeddings
    )

    assert len(results_user1) == 1
    assert results_user1[0].page_content == "用户1的私有内容"


def test_delete_document_vectors_removes_only_target_doc(persist_dir, fake_embeddings):
    chunks_a = _make_chunks(["要删除的文档内容"])
    chunks_b = _make_chunks(["保留的文档内容"])

    vector_store_service.add_document_chunks(
        user_id=1, doc_id="doc-del", chunks=chunks_a, embeddings=fake_embeddings
    )
    vector_store_service.add_document_chunks(
        user_id=1, doc_id="doc-keep", chunks=chunks_b, embeddings=fake_embeddings
    )

    vector_store_service.delete_document_vectors(
        user_id=1, doc_id="doc-del", embeddings=fake_embeddings
    )

    results_deleted = vector_store_service.similarity_search(
        user_id=1, doc_id="doc-del", query="内容", k=5, embeddings=fake_embeddings
    )
    results_kept = vector_store_service.similarity_search(
        user_id=1, doc_id="doc-keep", query="内容", k=5, embeddings=fake_embeddings
    )

    assert len(results_deleted) == 0
    assert len(results_kept) == 1
