import importlib.util
import json
from pathlib import Path


def load_builder():
    path = Path(__file__).resolve().parents[2] / 'scripts/build_rag_dataset.py'
    spec = importlib.util.spec_from_file_location('rag_builder', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_synthetic_dataset_matches_runtime_scope_contract():
    dataset = load_builder().build()
    assert len(dataset['cases']) >= 100
    assert all(1 <= len(case['doc_ids']) <= 10 for case in dataset['cases'])
    chunks = {chunk['id']: chunk for chunk in dataset['chunks']}
    for case in dataset['cases']:
        assert case['label_origin'] == 'synthetic_rule'
        for relevant in case['relevant']:
            assert chunks[relevant]['doc_id'] in case['doc_ids']
            assert chunks[relevant]['user_id'] == case['user_id']
            assert chunks[relevant]['split'] == case['split']


def test_topic_and_document_split_do_not_overlap():
    dataset = load_builder().build()
    for attribute in ('topic', 'doc_id'):
        groups = [{row[attribute] for row in dataset['chunks'] if row['split'] == split} for split in ('train', 'validation', 'test')]
        assert not groups[0] & groups[1] and not groups[0] & groups[2] and not groups[1] & groups[2]


def test_dataset_fingerprint_survives_git_line_endings():
    builder = load_builder()
    serialized = json.dumps(builder.build(), ensure_ascii=False, indent=2)
    assert builder.fingerprint(json.loads(serialized.replace('\n', '\r\n'))) == builder.fingerprint(json.loads(serialized))
