"""Public evidence contracts, shared by retrieval, tutoring and practice generation."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=1000)
    doc_ids: list[str] = Field(min_length=1, max_length=10)
    mode: Literal['dense', 'hybrid', 'rerank'] = 'rerank'


class Evidence(BaseModel):
    id: str
    source_type: Literal['private_document'] = 'private_document'
    doc_id: str
    chunk_id: str
    revision: int
    index_version: str
    file_name: str
    page: int = 0
    section: str = ''
    content: str
    content_hash: str


class RetrievalResult(BaseModel):
    query: str
    rewritten_query: str | None = None
    status: Literal['ok', 'empty', 'degraded', 'failed']
    evidence: list[Evidence]
    trace: dict


def evidence_from_row(row, label):
    meta = row['metadata']
    return Evidence(id=label, doc_id=row['doc_id'], chunk_id=row['chunk_id'], revision=row['revision'],
                    index_version=row['index_version'], file_name=row['file_name'],
                    content=row['content'], content_hash=meta.get('content_hash', ''),
                    page=meta.get('page', 0), section=meta.get('section', ''))
