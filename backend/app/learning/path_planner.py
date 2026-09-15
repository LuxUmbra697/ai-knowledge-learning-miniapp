"""Deterministic workload policy, separate from BKT estimates and FSRS scheduling."""
from graphlib import CycleError, TopologicalSorter

VERSION = 'prerequisite-workload-v1'


def graph(nodes, edges):
    if len(nodes) > 100 or len(edges) > 180 or len(set(nodes)) != len(nodes):
        raise ValueError('路径最多包含 100 个不同知识点和 180 条关系')
    parents = {key: set() for key in sorted(nodes)}
    for source, target in edges:
        if source not in parents or target not in parents:
            raise ValueError('关系引用了不存在或不属于本人的知识点')
        if source == target or source in parents[target]:
            raise ValueError('不能添加自身依赖或重复关系')
        parents[target].add(source)
    try:
        order = list(TopologicalSorter({key: sorted(values) for key, values in parents.items()}).static_order())
    except CycleError:
        raise ValueError('前置关系形成了环，请移除循环依赖') from None
    linked = {key for edge in edges for key in edge}
    return {'order': order, 'parents': {key: sorted(value) for key, value in parents.items()},
            'isolated': sorted(set(nodes) - linked)}


def recommend(concepts, cards, edges, budget, now):
    nodes = {node['concept_id']: node for node in concepts}
    structure = graph(list(nodes), edges)
    ancestors, blocked = {}, {}
    for key in structure['order']:
        ancestors[key] = set(structure['parents'][key])
        for parent in structure['parents'][key]:
            ancestors[key].update(ancestors[parent])
        blocked[key] = sorted(parent for parent in ancestors[key]
                              if nodes[parent]['attempts'] < 3 or nodes[parent]['mastery'] < .7)
    by_concept = {}
    for card in sorted(cards, key=lambda value: (value['due_at'], value['card_id'])):
        by_concept.setdefault(card['concept_id'], card)
    candidates = []
    for key in structure['order']:
        node, card = nodes[key], by_concept.get(key)
        if blocked[key] or not card:
            continue
        due = card['due_at'] <= now
        if not due and node['mastery'] >= .7 and node['attempts'] >= 3:
            continue
        overdue = max(0, (now - card['due_at']).days)
        supports = any(key in unmet for unmet in blocked.values())
        score = (4 + min(overdue, 7) / 7 + 1 - node['mastery']) if due else (2 * (1 - node['mastery']) + .5 * supports)
        kind = 'review' if due else 'read'
        candidates.append({'id': f'{kind}_{card["card_id"]}_{card["version"]}', 'kind': kind,
                           'concept_id': key, 'label': node['label'], 'card_id': card['card_id'],
                           'quiz_id': card['quiz_id'], 'question_id': card['question_id'], 'card_version': card['version'],
                           'minutes': 3 if due else 2, 'priority': round(score, 6),
                           'basis': {'due': due, 'overdue_days': overdue, 'mastery': node['mastery'],
                                     'attempts': node['attempts'], 'supports_prerequisite': supports}})
    items, spent = [], 0
    for item in sorted(candidates, key=lambda value: (-value['priority'], value['concept_id'])):
        if spent + item['minutes'] <= budget and len(items) < 10:
            items.append(item)
            spent += item['minutes']
    return {'items': items, 'minutes': spent, 'budget_minutes': budget, 'blocked': {key: values for key, values in blocked.items() if values},
            'order': structure['order'], 'isolated': structure['isolated'], 'algorithm_version': VERSION,
            'prerequisite_policy': {'minimum_observations': 3, 'mastery_threshold': .7},
            'time_estimates': 'Policy estimates: review 3 min, reading 2 min; not measured study time'}
