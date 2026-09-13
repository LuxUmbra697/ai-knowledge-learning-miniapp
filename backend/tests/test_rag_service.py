"""Private RAG regression: structured citations, fail-closed scope and no web export."""
import json
from unittest.mock import AsyncMock

from fastapi import HTTPException
import pytest

from app.models.evidence import Evidence, RetrievalResult
from app.core.exceptions import KnowledgeBaseError
from app.services import rag_service


def result(status='ok', content='原文证据'):
    evidence = [] if status in ('empty', 'failed') else [Evidence(id='E1', doc_id='doc_1', chunk_id='c1', revision=1,
                       index_version='v1', file_name='test.md', section='章节', content=content, content_hash='hash')]
    return RetrievalResult(query='学习', status=status, evidence=evidence, trace={})


@pytest.mark.asyncio
async def test_tool_returns_complete_structured_evidence(monkeypatch):
    retrieve = AsyncMock(return_value=result())
    monkeypatch.setattr(rag_service, 'retrieve', retrieve)
    data = await rag_service._build_knowledge_base_tool(1, 'doc_1').ainvoke({'query': '学习'})
    assert data['evidence'][0]['section'] == '章节'
    assert data['evidence'][0]['chunk_id'] == 'c1'
    retrieve.assert_awaited_once_with(1, ['doc_1'], '学习')


@pytest.mark.asyncio
async def test_tool_cannot_override_identity(monkeypatch):
    call = AsyncMock(); monkeypatch.setattr(rag_service, 'retrieve', call)
    with pytest.raises(ValueError):
        await rag_service._build_knowledge_base_tool(1, 'doc_1').ainvoke({'query': '学习', 'user_id': 2})
    call.assert_not_called()


@pytest.mark.parametrize('status', ['failed', 'empty'])
def test_no_evidence_never_becomes_an_unconstrained_generation_prompt(status):
    with pytest.raises(KnowledgeBaseError):
        rag_service.serialize_context(result(status))


def test_over_budget_source_is_not_silently_truncated():
    with pytest.raises(KnowledgeBaseError):
        rag_service.serialize_context(result(content='文' * 20000))


def test_context_is_valid_json_with_locations():
    data = json.loads(rag_service.serialize_context(result()))
    assert data['source_type'] == 'private_document'
    assert data['evidence'][0]['content'] == '原文证据'
    assert data['evidence'][0]['revision'] == 1


@pytest.mark.asyncio
async def test_scope_error_does_not_fall_back_to_web(monkeypatch):
    monkeypatch.setattr(rag_service, 'retrieve', AsyncMock(side_effect=HTTPException(404)))
    with pytest.raises(HTTPException):
        await rag_service.fetch_rag_context('private', 1, 'doc_1')


@pytest.mark.asyncio
async def test_timeout_is_not_treated_as_absent_knowledge(monkeypatch):
    monkeypatch.setattr(rag_service, 'retrieve', AsyncMock(side_effect=TimeoutError()))
    with pytest.raises(TimeoutError):
        await rag_service.fetch_rag_context('private', 1, 'doc_1')


@pytest.mark.asyncio
async def test_private_retrieval_does_not_construct_a_web_agent(monkeypatch):
    monkeypatch.setattr(rag_service, 'retrieve', AsyncMock(return_value=result()))
    monkeypatch.setenv('ENABLE_WEB_SEARCH', 'true')
    data = json.loads(await rag_service.fetch_rag_context('private', 1, 'doc_1'))
    assert all(item['source_type'] == 'private_document' for item in data['evidence'])


def test_degraded_retrieval_is_explicit_in_context():
    assert json.loads(rag_service.serialize_context(result('degraded')))['retrieval_status'] == 'degraded'
