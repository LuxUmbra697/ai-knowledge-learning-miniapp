from datetime import datetime, timedelta, timezone

import pytest


def test_dag_rejects_cycles_self_links_duplicates_and_missing_nodes():
    from app.learning.path_planner import graph
    for edges in ([['a', 'a']], [['a', 'b'], ['b', 'a']], [['a', 'missing']], [['a', 'b'], ['a', 'b']]):
        with pytest.raises(ValueError):
            graph(['a', 'b'], edges)
    result = graph(['c', 'b', 'a'], [['a', 'b']])
    assert result['order'].index('a') < result['order'].index('b')
    assert result['isolated'] == ['c']


def test_plan_balances_due_weakness_prerequisites_and_bounded_workload():
    from app.learning.path_planner import recommend
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    concepts = [{'concept_id': name, 'label': name, 'mastery': mastery, 'attempts': n}
                for name, mastery, n in [('a', .3, 1), ('b', .2, 1), ('c', .8, 4)]]
    cards = [{'card_id': f'card_{name}', 'concept_id': name, 'quiz_id': 'quiz_fixture', 'question_id': name,
              'version': 1, 'due_at': now - timedelta(days=2)} for name in ['a', 'b', 'c']]
    result = recommend(concepts, cards, [['a', 'b']], 6, now)
    assert [item['concept_id'] for item in result['items']] == ['a', 'c']
    assert result['minutes'] <= 6 and result['blocked']['b'] == ['a']
    assert all(item['kind'] == 'review' and item['basis']['due'] for item in result['items'])
    concepts[0].update(mastery=.8, attempts=3)
    unlocked = recommend(concepts, cards, [['a', 'b']], 3, now)
    assert unlocked['items'][0]['concept_id'] == 'b'
    assert recommend([], [], [], 15, now)['items'] == []


def test_not_due_study_is_not_a_review_or_a_fabricated_mastery_observation():
    from app.learning.path_planner import recommend
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    result = recommend([{'concept_id': 'a', 'label': 'a', 'mastery': .2, 'attempts': 1}],
                       [{'card_id': 'card_a', 'concept_id': 'a', 'quiz_id': 'quiz_a', 'question_id': 'q1', 'version': 1,
                         'due_at': now + timedelta(days=1)}], [], 5, now)
    assert result['items'][0]['kind'] == 'read'
    assert result['items'][0]['basis']['attempts'] == 1
    assert result['items'][0]['minutes'] == 2


def test_plan_commands_reject_implicit_consent_identity_and_unbounded_ids():
    from pydantic import ValidationError
    from app.models.learning_path import PathUpdate, PlanConfirm
    for changes in ({'confirmed': False}, {'confirmed': 'true'}, {'minutes': True}, {'minutes': 61}, {'user_id': 99}):
        with pytest.raises(ValidationError):
            PlanConfirm.model_validate({'fingerprint': 'a' * 64, 'minutes': 15, 'confirmed': True, **changes})
    with pytest.raises(ValidationError):
        PathUpdate(version=0, edges=[('a' * 10000, 'b')])
