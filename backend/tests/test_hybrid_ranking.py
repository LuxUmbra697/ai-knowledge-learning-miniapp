import pytest
from app.services.hybrid_ranking import tokenize, reciprocal_rank_fusion, bm25_rank, rerank_lexical


def test_chinese_bigrams_and_ascii_terms_are_normalized():
    assert '后进' in tokenize('栈遵循后进先出原则，Python LIST')
    assert 'python' in tokenize('栈遵循后进先出原则，Python LIST')
    assert 'list' in tokenize('LIST')


def test_rrf_combines_ranks_not_incomparable_raw_scores():
    result = reciprocal_rank_fusion([['a', 'b', 'c'], ['b', 'd', 'a']], k=60)
    assert result[0][0] == 'b'
    assert dict(result)['b'] == pytest.approx(1/62 + 1/61)
    assert dict(reciprocal_rank_fusion([['a', 'a', 'b']]))['a'] == pytest.approx(1/61)


def test_bm25_retrieves_chinese_document_and_empty_query_returns_none():
    corpus = {'stack': '栈的特性是后进先出。', 'queue': '队列按先进先出的顺序工作。', 'tree': '树是一种层级数据结构。'}
    assert bm25_rank('后进先出', corpus)[0] == 'stack'
    assert bm25_rank('', corpus) == []
    assert bm25_rank('不存在的词xyz', {'english': 'hello world'}) == []


def test_reranker_is_bounded_and_never_introduces_new_evidence():
    corpus = {'a': '队列先入先出', 'b': '栈后进先出', 'c': '树形结构'}
    reranked = rerank_lexical('栈后进先出', [('a', .03), ('b', .02)], corpus, limit=2)
    assert reranked[0] == 'b'
    assert set(reranked) == {'a', 'b'}
