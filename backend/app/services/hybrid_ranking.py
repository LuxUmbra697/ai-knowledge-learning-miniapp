"""Chinese bigram BM25, rank-only fusion, and a transparent lightweight reranker."""
from collections import defaultdict
import re

from rank_bm25 import BM25Okapi


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r'[a-z0-9_]+', text.lower())
    for sequence in re.findall(r'[\u3400-\u9fff]+', text):
        tokens.extend(sequence if len(sequence) == 1 else [sequence[index:index+2] for index in range(len(sequence) - 1)])
    return tokens


def bm25_rank(query: str, corpus: dict[str, str], limit: int = 20) -> list[str]:
    query_tokens = tokenize(query)
    if not query_tokens or not corpus:
        return []
    ids = sorted(corpus)
    tokenized = [tokenize(corpus[key]) or ['__empty_document__'] for key in ids]
    scores = BM25Okapi(tokenized, k1=1.5, b=.75).get_scores(query_tokens)
    candidates = [(key, float(scores[index])) for index, key in enumerate(ids) if set(query_tokens).intersection(tokenized[index])]
    return [key for key, _score in sorted(candidates, key=lambda item: (-item[1], item[0]))[:limit]]


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    if k < 1:
        raise ValueError('RRF k must be positive')
    scores = defaultdict(float)
    for ranking in rankings:
        seen = set()
        for position, key in enumerate(ranking, 1):
            if key in seen:
                continue
            seen.add(key)
            scores[key] += 1 / (k + position)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def rerank_lexical(query: str, candidates: list[tuple[str, float]], corpus: dict[str, str], limit: int = 20) -> list[str]:
    """Rule-based candidate reranking, not a neural cross-encoder or trained model."""
    query_terms = set(tokenize(query))
    selected = candidates[:max(0, min(limit, 50))]
    def score(item):
        key, fused = item
        terms = set(tokenize(corpus[key]))
        coverage = len(terms & query_terms) / max(len(query_terms), 1)
        return (-.8 * coverage - .2 * min(fused * 30, 1), key)
    return [key for key, _ in sorted(selected, key=score)]
