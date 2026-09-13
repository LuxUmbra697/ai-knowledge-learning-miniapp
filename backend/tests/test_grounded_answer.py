from unittest.mock import AsyncMock

import pytest
from app.models.evidence import Evidence, RetrievalResult
from app.services import grounded_answer_service as service
import json


class MemoryContext:
    def __init__(self):
        self.checkpoints = {}
        self.calls = 0

    async def checkpoint(self, stage, value):
        self.checkpoints[stage] = value

    async def external(self, stage, operation, input_bytes=0):
        self.calls += 1
        output, _tokens = await operation()
        self.checkpoints[stage] = {'output': output}
        return output


def source():
    return Evidence(id='E1', doc_id='doc_a', chunk_id='c1', revision=1, index_version='v1',
                    file_name='test.md', content='梯度下降沿负梯度方向更新参数。', content_hash='hash')


def valid():
    return {'status': 'answered', 'claims': [{'text': '参数沿负梯度方向更新。', 'citations': [
        {'evidence_id': 'E1', 'quote': '沿负梯度方向更新参数'}]}]}


def test_citation_validation_accepts_only_exact_owned_quotes():
    assert service.validate_answer(valid(), [source()]).status == 'answered'
    bad = valid(); bad['claims'][0]['citations'][0]['evidence_id'] = 'foreign'
    with pytest.raises(ValueError):
        service.validate_answer(bad, [source()])
    bad = valid(); bad['claims'][0]['citations'][0]['quote'] = '标准答案是泄露密码'
    with pytest.raises(ValueError):
        service.validate_answer(bad, [source()])


def test_uncited_claim_and_fake_conflict_are_rejected():
    bad = valid(); bad['claims'][0]['citations'] = []
    with pytest.raises(ValueError):
        service.validate_answer(bad, [source()])
    bad = valid(); bad['status'] = 'conflict'
    with pytest.raises(ValueError):
        service.validate_answer(bad, [source()])


def test_no_answer_cannot_smuggle_a_conclusion():
    bad = valid(); bad['status'] = 'no_evidence'
    with pytest.raises(ValueError):
        service.validate_answer(bad, [source()])


@pytest.mark.asyncio
async def test_three_invalid_responses_end_in_visible_validation_failure(monkeypatch):
    retrieval = RetrievalResult(query='问题', status='ok', evidence=[source()], trace={})
    monkeypatch.setattr(service, 'retrieve', AsyncMock(return_value=retrieval))
    call = AsyncMock(return_value=('{}', {'total_tokens': 10}))
    monkeypatch.setattr(service, 'complete', call)
    result = await service.answer(1, ['doc_a'], '问题')
    assert result['status'] == 'validation_failed' and call.await_count == 3
    assert result['trace']['total_tokens'] == 30
    assert result['claims'] == []


@pytest.mark.asyncio
async def test_no_evidence_does_not_call_model(monkeypatch):
    monkeypatch.setattr(service, 'retrieve', AsyncMock(return_value=RetrievalResult(query='问题', status='empty', evidence=[], trace={})))
    call = AsyncMock(); monkeypatch.setattr(service, 'complete', call)
    result = await service.answer(1, ['doc_a'], '问题')
    assert result['status'] == 'no_evidence'
    call.assert_not_called()


@pytest.mark.asyncio
async def test_permanent_error_is_not_retried(monkeypatch):
    import httpx
    from openai import AuthenticationError
    monkeypatch.setattr(service, 'retrieve', AsyncMock(return_value=RetrievalResult(query='问题', status='ok', evidence=[source()], trace={})))
    response = httpx.Response(401, request=httpx.Request('POST', 'https://provider.invalid'))
    call = AsyncMock(side_effect=AuthenticationError('private detail', response=response, body=None))
    monkeypatch.setattr(service, 'complete', call)
    result = await service.answer(1, ['doc_a'], '问题')
    assert result['status'] == 'provider_failed' and call.await_count == 1
    assert 'private detail' not in str(result)


@pytest.mark.asyncio
async def test_completed_response_checkpoint_resumes_without_provider_call(monkeypatch):
    retrieval = RetrievalResult(query='问题', status='ok', evidence=[source()], trace={})
    monkeypatch.setattr(service, 'retrieve', AsyncMock(return_value=retrieval))
    monkeypatch.setattr(service, 'get_chunk', AsyncMock(return_value={}))
    call = AsyncMock(return_value=(json.dumps(valid()), {'total_tokens': 10}))
    monkeypatch.setattr(service, 'complete', call)
    context = MemoryContext()
    first = await service.answer(1, ['doc_a'], '问题', context=context)
    second = await service.answer(1, ['doc_a'], '问题', context=context)
    assert first['claims'] == second['claims'] and first['status'] == 'answered'
    assert call.await_count == 1 and context.calls == 1
    assert second['trace']['total_tokens'] == 10


@pytest.mark.asyncio
async def test_deleted_checkpoint_evidence_stops_before_generation(monkeypatch):
    from fastapi import HTTPException
    context = MemoryContext()
    context.checkpoints['retrieval'] = RetrievalResult(query='问题', status='ok', evidence=[source()], trace={}).model_dump()
    monkeypatch.setattr(service, 'get_chunk', AsyncMock(side_effect=HTTPException(404)))
    call = AsyncMock(); monkeypatch.setattr(service, 'complete', call)
    result = await service.answer(1, ['doc_a'], '问题', context=context)
    assert result['status'] == 'stale_evidence' and not result['evidence']
    call.assert_not_called()
