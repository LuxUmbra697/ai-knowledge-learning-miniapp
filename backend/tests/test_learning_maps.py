import pytest
from app.learning.maps import build_map, validate_map


def fixture():
    questions = [{'id': 'q1', 'stem': '为什么需要回忆？', 'knowledge_point': '主动回忆', 'citations': []},
                 {'id': 'q2', 'stem': '怎样检验理解？', 'knowledge_point': '主动回忆', 'citations': [
                     {'status': 'verified', 'doc_id': 'd1', 'chunk_id': 'c1', 'revision': 1,
                      'file_name': '公开样例.md', 'page': 0, 'section': '方法'}]}]
    records = [{'question_id': 'q1', 'is_correct': False}, {'question_id': 'q2', 'is_correct': True}]
    return questions, records


def test_maps_group_observed_tags_and_retain_only_current_sources():
    questions, records = fixture()
    data = build_map('title', questions, records)
    assert data == build_map('title', questions, records)
    assert len([n for n in data['nodes'] if n['kind'] == 'concept']) == 1
    assert len([n for n in data['nodes'] if n['kind'] == 'source']) == 1
    assert next(n for n in data['nodes'] if n.get('question_id') == 'q1')['state'] == 'wrong'
    assert {e['relation'] for e in data['edges']} == {'contains', 'assesses', 'supported_by'}
    assert all('prerequisite' not in str(item) for item in data['edges'])
    questions[1]['citations'][0] = {'status': 'unavailable'}
    changed = build_map('title', questions, records)
    assert not any(n['kind'] == 'source' for n in changed['nodes'])
    assert changed['source_hash'] != data['source_hash']


def test_maps_require_complete_authoritative_records():
    questions, records = fixture()
    for attempts in ([], records[:1], [records[0], records[0]], records + [records[0]]):
        with pytest.raises(ValueError):
            build_map('title', questions, attempts)


def test_graph_contract_rejects_dangling_edges_cycles_and_injected_ids():
    data = build_map('title', *fixture())
    data['edges'].append({'source': 'missing', 'target': 'root', 'relation': 'contains'})
    with pytest.raises(ValueError):
        validate_map(data)
    data = build_map('title', *fixture())
    data['edges'].append({'source': 'q0', 'target': 'root', 'relation': 'contains'})
    with pytest.raises(ValueError):
        validate_map(data)
    data = build_map('title', *fixture())
    data['nodes'][0]['id'] = 'root\nclick root "https://example.invalid"'
    with pytest.raises(ValueError):
        validate_map(data)
