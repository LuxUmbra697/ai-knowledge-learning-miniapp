"""Versioned, evidence-linked study maps derived from saved attempts, not generated syntax."""
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Node(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^(root|[cqs][0-9]+)$')
    kind: Literal['topic', 'concept', 'question', 'source']
    label: str = Field(min_length=1, max_length=120)
    detail: str = Field(default='', max_length=4000)
    state: Literal['neutral', 'correct', 'wrong'] = 'neutral'
    question_id: str | None = None
    doc_id: str | None = None
    chunk_id: str | None = None
    revision: int | None = None


class Edge(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source: str
    target: str
    relation: Literal['contains', 'assesses', 'supported_by']


class LearningMap(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal['study-map-v1'] = 'study-map-v1'
    source_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    mapping_basis: Literal['generated-question-tags'] = 'generated-question-tags'
    nodes: list[Node] = Field(min_length=1, max_length=121)
    edges: list[Edge] = Field(max_length=180)


def validate_map(data):
    graph = LearningMap.model_validate(data)
    ids = {node.id for node in graph.nodes}
    if len(ids) != len(graph.nodes) or 'root' not in ids:
        raise ValueError('Duplicate nodes or missing root')
    adjacency = {key: [] for key in ids}
    indegree = dict.fromkeys(ids, 0)
    for edge in graph.edges:
        if edge.source not in ids or edge.target not in ids:
            raise ValueError('Dangling graph edge')
        adjacency[edge.source].append(edge.target)
        indegree[edge.target] += 1
    queue = [key for key in ids if not indegree[key]]
    visited = 0
    while queue:
        current = queue.pop()
        visited += 1
        for target in adjacency[current]:
            indegree[target] -= 1
            if not indegree[target]:
                queue.append(target)
    if visited != len(ids):
        raise ValueError('Cycle in study hierarchy')
    return graph.model_dump()


def build_map(title, questions, records):
    attempts = {record['question_id']: record for record in records}
    if (not 1 <= len(questions) <= 20 or len(attempts) != len(records)
            or set(attempts) != {q['id'] for q in questions}):
        raise ValueError('Complete unique authoritative attempts are required')
    nodes = [{'id': 'root', 'kind': 'topic', 'label': title[:120] or '本次学习'}]
    edges, concepts, sources = [], {}, {}
    for index, question in enumerate(questions):
        label = question.get('knowledge_point', '').strip()[:120] or '未标注知识点'
        if label not in concepts:
            concept = f'c{len(concepts)}'
            concepts[label] = concept
            nodes.append({'id': concept, 'kind': 'concept', 'label': label})
            edges.append({'source': 'root', 'target': concept, 'relation': 'contains'})
        qid = f'q{index}'
        state = 'correct' if attempts[question['id']]['is_correct'] else 'wrong'
        nodes.append({'id': qid, 'kind': 'question', 'label': f'第 {index + 1} 题 · ' + ('已答对' if state == 'correct' else '需巩固'),
                      'detail': question['stem'][:4000], 'state': state, 'question_id': question['id']})
        edges.append({'source': concepts[label], 'target': qid, 'relation': 'assesses'})
        for citation in question.get('citations', []):
            if citation.get('status') != 'verified' or not citation.get('doc_id') or not citation.get('chunk_id'):
                continue
            key = (citation['doc_id'], citation['chunk_id'], citation['revision'])
            if key not in sources:
                sid = f's{len(sources)}'
                sources[key] = sid
                location = f"第 {citation['page']} 页" if citation.get('page') else citation.get('section', '')
                nodes.append({'id': sid, 'kind': 'source', 'label': (citation.get('file_name', '原文') + ' · ' + location)[:120],
                              'doc_id': key[0], 'chunk_id': key[1], 'revision': key[2]})
            edge = {'source': qid, 'target': sources[key], 'relation': 'supported_by'}
            if edge not in edges:
                edges.append(edge)
    digest = hashlib.sha256(json.dumps([nodes, edges], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return validate_map({'nodes': nodes, 'edges': edges, 'source_hash': digest})
