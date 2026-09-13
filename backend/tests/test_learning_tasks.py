from unittest.mock import AsyncMock

from fastapi import HTTPException
import pytest

from app.models.evidence import RetrievalRequest
from app.services import learning_task_service as service


@pytest.mark.asyncio
async def test_task_admission_checks_scope_before_enqueue(monkeypatch):
    monkeypatch.setattr(service.index, 'scoped_chunks', AsyncMock(side_effect=HTTPException(404)))
    enqueue = AsyncMock(); monkeypatch.setattr(service.jobs, 'enqueue', enqueue)
    with pytest.raises(HTTPException):
        await service.create_answer(1, RetrievalRequest(query='question', doc_ids=['other-document']), 'request-key')
    enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_task_admission_canonicalizes_document_order_and_records_revision(monkeypatch):
    monkeypatch.setattr(service.index, 'scoped_chunks', AsyncMock(return_value=[
        {'doc_id': 'b', 'revision': 2, 'index_version': 'v1'}, {'doc_id': 'a', 'revision': 1, 'index_version': 'v1'}]))
    enqueue = AsyncMock(return_value={'task_id': 'task'}); monkeypatch.setattr(service.jobs, 'enqueue', enqueue)
    await service.create_answer(1, RetrievalRequest(query='question', doc_ids=['b', 'a', 'b']), 'request-key')
    args = enqueue.call_args.args
    assert args[:2] == (1, 'answer') and args[3] == 'request-key'
    assert args[2]['doc_ids'] == ['a', 'b']
    assert args[2]['scope'] == [('a', 1, 'v1'), ('b', 2, 'v1')]
