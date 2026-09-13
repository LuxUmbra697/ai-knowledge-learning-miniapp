"""Reproduce actual Chroma retrieval from cached synthetic embeddings, with no external calls."""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import uuid

import numpy as np
from build_rag_dataset import fingerprint

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ.update(AI_LEARN_ENV_FILE='', ANONYMIZED_TELEMETRY='false')
from app.core.config import Settings  # noqa: E402
from app.services import vector_store_service as vector  # noqa: E402
from app.services.hybrid_ranking import bm25_rank, reciprocal_rank_fusion, rerank_lexical  # noqa: E402
from langchain_core.documents import Document  # noqa: E402
from langchain_core.embeddings import Embeddings  # noqa: E402


def metrics(ranking, relevant, k=4):
    expected = set(relevant)
    hits = [int(key in expected) for key in ranking[:k]]
    recall = len(set(ranking[:k]) & expected) / len(expected) if expected else None
    mrr = next((1/(index+1) for index, key in enumerate(ranking) if key in expected), 0) if expected else None
    ideal = sum(1/math.log2(index+2) for index in range(min(len(expected), k)))
    ndcg = sum(hit/math.log2(index+2) for index, hit in enumerate(hits)) / ideal if ideal else None
    return dict(recall_at_4=recall, mrr=mrr, ndcg_at_4=ndcg)


class CachedEmbeddings(Embeddings):
    def __init__(self, cache):
        self.cache = cache

    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text):
        return self.cache[hashlib.sha256(text.encode()).hexdigest()].tolist()


def main():
    dataset_path = ROOT / 'eval/rag/dataset-v1.json'
    dataset = json.loads(dataset_path.read_text(encoding='utf-8'))
    metadata = json.loads((ROOT / 'eval/rag/embedding-v1.json').read_text())
    assert metadata['dataset_sha256'] == fingerprint(dataset)
    embeddings = CachedEmbeddings(dict(np.load(ROOT / 'eval/rag/embedding-v1.npz', allow_pickle=False)))
    settings = Settings(_env_file=None, dashscope_embedding_model=metadata['model'], embedding_dimensions=metadata['dimensions'],
                         chroma_persist_dir=str(ROOT / '.local/eval' / uuid.uuid4().hex))
    vector.get_settings = lambda: settings
    documents = {}
    for chunk in dataset['chunks']:
        documents.setdefault(chunk['doc_id'], []).append(chunk)
    version = vector.index_version()
    for doc_id, chunks in documents.items():
        vector.add_document_chunks(chunks[0]['user_id'], doc_id,
            [Document(page_content=row['text'], metadata={'chunk_id': row['id']}) for row in chunks], embeddings)

    raw = []
    for mode in ('dense', 'hybrid', 'rerank'):
        for case in dataset['cases']:
            started = time.perf_counter()
            authorized = all(doc_id in documents and documents[doc_id][0]['user_id'] == case['user_id'] for doc_id in case['doc_ids'])
            if not authorized:
                raw.append(dict(mode=mode, case_id=case['id'], split=case['split'], category=case['category'],
                                expected=case['expected'], forbidden=True, ranking=[], latency_ms=0))
                continue
            owned = [chunk for doc_id in case['doc_ids'] for chunk in documents[doc_id]]
            corpus = {row['id']: row['text'] for row in owned}
            scopes = [vector.scope_key(doc_id, 1, version) for doc_id in case['doc_ids']]
            dense = [item.metadata['chunk_id'] for item in vector.search_scoped(case['user_id'], scopes, case['query'], 20, embeddings)]
            assert set(dense) <= set(corpus)
            ranking = dense
            if mode != 'dense':
                lexical = bm25_rank(case['query'], corpus, 20)
                fused = reciprocal_rank_fusion([dense, lexical])
                ranking = rerank_lexical(case['query'], fused, corpus, 20) if mode == 'rerank' else [key for key, _score in fused]
            raw.append(dict(mode=mode, case_id=case['id'], split=case['split'], category=case['category'], expected=case['expected'],
                            forbidden=False, ranking=ranking[:4], latency_ms=round((time.perf_counter()-started)*1000, 2),
                            scope_valid=all(key in corpus for key in ranking[:4]), **metrics(ranking, case['relevant'])))
    summary = []
    for mode in ('dense', 'hybrid', 'rerank'):
        for split in ('all', 'train', 'validation', 'test'):
            rows = [row for row in raw if row['mode'] == mode and (split == 'all' or row['split'] == split)]
            positive = [row for row in rows if row.get('recall_at_4') is not None]
            authorized = [row for row in rows if not row['forbidden']]
            no_answer = [row for row in authorized if row['expected'] == 'no_answer']
            summary.append(dict(mode=mode, split=split, cases=len(rows), answerable_cases=len(positive),
                                **{key: round(float(np.mean([row[key] for row in positive])), 6) for key in ('recall_at_4', 'mrr', 'ndcg_at_4')},
                                candidate_scope_validity=all(row['scope_valid'] for row in authorized),
                                forbidden_cases_blocked=sum(row['forbidden'] and row['expected'] == 'forbidden' for row in rows),
                                no_answer_empty_retrieval_rate=sum(not row['ranking'] for row in no_answer)/len(no_answer),
                                cached_retrieval_p50_ms=round(float(np.median([row['latency_ms'] for row in authorized])), 2),
                                cached_retrieval_p95_ms=round(float(np.percentile([row['latency_ms'] for row in authorized], 95)), 2)))
    report = dict(dataset_version=dataset['version'], dataset_sha256=metadata['dataset_sha256'], seed=dataset['seed'],
                  recorded_at=datetime.now(timezone.utc).isoformat(), model=metadata['model'], dimensions=metadata['dimensions'],
                  parameters={'rrf_k': 60, 'candidates': 20, 'top_k': 4, 'reranker': 'lexical-v1'},
                  embedding_acquisition={'requests': len(metadata['requests']), 'total_tokens': sum(row['total_tokens'] for row in metadata['requests']), 'billed_currency': None},
                  evaluation_external_calls=0, summary=summary,
                  limitations=['Synthetic rule labels, not human correctness ratings.',
                               'Cached query embedding; latency excludes network/provider time.',
                               'Candidate scope checks are not answer entailment checks.',
                               'Retrieval alone does not decide no-answer or resolve conflicts.',
                               'Shared query templates limit generalization claims. No tuning/training performed.'])
    (ROOT / 'eval/rag/results-v1.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    (ROOT / 'eval/rag/raw-v1.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in raw), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
