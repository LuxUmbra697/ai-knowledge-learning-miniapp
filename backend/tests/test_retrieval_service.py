from unittest.mock import AsyncMock, Mock

from fastapi import HTTPException
from langchain_core.documents import Document
import pytest

from app.services import retrieval_service as service


def chunk(doc='doc_a', key='c1', text='梯度下降沿负梯度方向更新参数。'):
    return dict(doc_id=doc, chunk_id=key, revision=1, index_version='v1', file_name='学习笔记.md',
                content=text, metadata={'page': 0, 'section': '优化', 'content_hash': 'abc'})


@pytest.mark.asyncio
async def test_unowned_scope_never_reaches_dense_or_reranker(monkeypatch):
    monkeypatch.setattr(service.repo, 'scoped_chunks', AsyncMock(side_effect=HTTPException(404)))
    dense = Mock(); rank = Mock()
    monkeypatch.setattr(service.vector, 'search_scoped', dense)
    monkeypatch.setattr(service, 'rerank_lexical', rank)
    with pytest.raises(HTTPException):
        await service.retrieve(2, ['doc_a'], '梯度下降')
    dense.assert_not_called(); rank.assert_not_called()


@pytest.mark.asyncio
async def test_scope_precedes_every_recall_path_and_evidence_is_structured(monkeypatch):
    rows = [chunk(), chunk('doc_a', 'c2', '学习率决定更新步长。')]
    monkeypatch.setattr(service.repo, 'scoped_chunks', AsyncMock(return_value=rows))
    dense = Mock(return_value=[Document(page_content='不可信的向量正文', metadata={'doc_id': 'doc_a', 'chunk_id': 'c1', 'revision': 1}),
                              Document(page_content='其他用户内容', metadata={'doc_id': 'other', 'chunk_id': 'secret', 'revision': 1})])
    monkeypatch.setattr(service.vector, 'search_scoped', dense)
    result = await service.retrieve(1, ['doc_a'], '梯度下降')
    assert dense.call_args.args[:2] == (1, ['doc_a:1:v1'])
    assert all(e.doc_id == 'doc_a' for e in result.evidence)
    assert result.evidence[0].content == rows[0]['content']
    assert result.evidence[0].section == '优化'
    assert '不可信' not in result.model_dump_json()
    assert result.trace['reranker'] == 'lexical'


@pytest.mark.asyncio
async def test_dense_failure_is_explicit_not_empty_knowledge(monkeypatch):
    monkeypatch.setattr(service.repo, 'scoped_chunks', AsyncMock(return_value=[chunk()]))
    monkeypatch.setattr(service.vector, 'search_scoped', Mock(side_effect=TimeoutError('secret provider URL')))
    result = await service.retrieve(1, ['doc_a'], '梯度下降')
    assert result.status == 'degraded'
    assert result.trace['dense_error'] == 'TimeoutError'
    assert result.evidence
    assert 'secret' not in result.model_dump_json()


@pytest.mark.asyncio
async def test_dense_only_failure_does_not_silently_use_bm25(monkeypatch):
    monkeypatch.setattr(service.repo, 'scoped_chunks', AsyncMock(return_value=[chunk()]))
    monkeypatch.setattr(service.vector, 'search_scoped', Mock(side_effect=TimeoutError()))
    result = await service.retrieve(1, ['doc_a'], '梯度下降', mode='dense')
    assert result.status == 'failed' and result.evidence == []
