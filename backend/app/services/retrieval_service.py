"""Pre-filtered dense/BM25 retrieval with RRF and observable bounded reranking."""
import asyncio
from time import perf_counter
import uuid

from app.core.config import get_settings
from app.models.evidence import RetrievalResult, evidence_from_row
from app.repositories import rag_index_repository as repo
from app.services import vector_store_service as vector
from app.services.hybrid_ranking import bm25_rank, reciprocal_rank_fusion, rerank_lexical


def chunk_key(row):
    return f'{row["doc_id"]}:{row["revision"]}:{row["chunk_id"]}'


async def retrieve(user_id: int, doc_ids: list[str], query: str, mode='rerank') -> RetrievalResult:
    started = perf_counter()
    settings = get_settings()
    version = vector.index_version()
    rows = await repo.scoped_chunks(user_id, doc_ids, version, settings.kb_max_corpus_chunks)
    by_key = {chunk_key(row): row for row in rows}
    corpus = {key: row['content'] for key, row in by_key.items()}
    scopes = sorted({vector.scope_key(row['doc_id'], row['revision'], row['index_version']) for row in rows})
    trace = dict(trace_id=uuid.uuid4().hex, index_version=version, mode=mode, scope_documents=len(doc_ids),
                 corpus_chunks=len(rows), candidates=settings.kb_retrieve_candidates,
                 rrf_k=60, reranker='none', embedding_calls=int(bool(rows)), dense_error=None)
    dense_ids, lexical_ids = [], []
    dense_started = perf_counter()
    if rows:
        try:
            dense = await asyncio.to_thread(vector.search_scoped, user_id, scopes, query, settings.kb_retrieve_candidates)
            dense_ids = list(dict.fromkeys(chunk_key(item.metadata) for item in dense if chunk_key(item.metadata) in by_key))
        except Exception as error:
            trace['dense_error'] = type(error).__name__
    trace['dense_ms'] = round((perf_counter() - dense_started) * 1000, 2)
    if mode != 'dense':
        lexical_ids = await asyncio.to_thread(bm25_rank, query, corpus, settings.kb_retrieve_candidates)
    if mode == 'dense':
        ranked = dense_ids
    else:
        fused = reciprocal_rank_fusion([dense_ids, lexical_ids])
        ranked = [key for key, _score in fused]
        if mode == 'rerank' and settings.kb_reranker == 'lexical':
            rerank_started = perf_counter()
            ranked = rerank_lexical(query, fused, corpus, settings.kb_retrieve_candidates)
            trace.update(reranker='lexical', rerank_ms=round((perf_counter() - rerank_started) * 1000, 2))
    selected = ranked[:settings.kb_retrieve_top_k]
    trace.update(dense_candidates=len(dense_ids), bm25_candidates=len(lexical_ids),
                 total_ms=round((perf_counter() - started) * 1000, 2))
    status = ('degraded' if selected else 'failed') if trace['dense_error'] else ('ok' if selected else 'empty')
    return RetrievalResult(query=query, status=status, trace=trace,
                           evidence=[evidence_from_row(by_key[key], f'E{index}') for index, key in enumerate(selected, 1)])
