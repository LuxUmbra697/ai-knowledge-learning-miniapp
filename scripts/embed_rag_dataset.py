"""Explicitly budgeted embedding of public synthetic fixtures, resumable without repeated batches."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from openai import OpenAI
from build_rag_dataset import fingerprint

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.core.config import get_settings  # noqa: E402


def main():
    settings = get_settings()
    dataset_path = ROOT / 'eval/rag/dataset-v1.json'
    dataset = json.loads(dataset_path.read_text(encoding='utf-8'))
    digest = fingerprint(dataset)
    texts = sorted(set([row['text'] for row in dataset['chunks']] + [case['query'] for case in dataset['cases'] if case['expected'] != 'forbidden']))
    assert len(texts) <= 160 and sum(len(text) for text in texts) <= 30000
    metadata_path = ROOT / 'eval/rag/embedding-v1.json'
    cache_path = ROOT / 'eval/rag/embedding-v1.npz'
    previous = json.loads(metadata_path.read_text()) if metadata_path.exists() else None
    if previous:
        assert (previous['model'], previous['dimensions']) == (settings.dashscope_embedding_model, settings.embedding_dimensions)
    cache = dict(np.load(cache_path, allow_pickle=False)) if cache_path.exists() else {}
    report = previous or dict(dataset_sha256=digest, model=settings.dashscope_embedding_model, dimensions=settings.embedding_dimensions,
                              source='public synthetic fixtures only', requests=[], billed_currency=None)
    missing = [text for text in texts if hashlib.sha256(text.encode()).hexdigest() not in cache]
    assert len(report['requests']) + (len(missing)+9)//10 <= 16
    with OpenAI(api_key=settings.dashscope_api_key, base_url=settings.dashscope_base_url, timeout=20, max_retries=0) as client:
        for offset in range(0, len(missing), 10):
            batch = missing[offset:offset+10]
            started = time.perf_counter()
            result = client.embeddings.create(model=settings.dashscope_embedding_model, input=batch, dimensions=settings.embedding_dimensions)
            assert len(result.data) == len(batch)
            for item in result.data:
                vector = np.asarray(item.embedding, dtype=np.float32)
                assert vector.shape == (settings.embedding_dimensions,) and np.isfinite(vector).all()
                cache[hashlib.sha256(batch[item.index].encode()).hexdigest()] = vector
            report['requests'].append(dict(inputs=len(batch), latency_ms=round((time.perf_counter()-started)*1000, 2),
                                           total_tokens=result.usage.total_tokens))
            report['recorded_at'] = datetime.now(timezone.utc).isoformat()
            np.savez_compressed(cache_path, **cache)
            metadata_path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    report['dataset_sha256'] = digest
    report['text_corpus_sha256'] = hashlib.sha256(json.dumps(texts, ensure_ascii=False).encode()).hexdigest()
    metadata_path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(cached_texts=len(cache), requests=len(report['requests']),
                         total_tokens=sum(row['total_tokens'] for row in report['requests']))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--confirm-max-16-batches', action='store_true', required=True)
    parser.parse_args()
    main()
