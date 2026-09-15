"""Deterministic scheduling and transparent knowledge-tracing contracts."""
from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 9, 14, 15, 55, tzinfo=timezone.utc)


def test_fsrs_schedule_is_reproducible_serializable_and_distinguishes_failure():
    from app.learning.scheduler import review
    good = review(None, 'card_synthetic', True, NOW)
    again = review(None, 'card_synthetic', False, NOW)
    assert good == review(None, 'card_synthetic', True, NOW)
    assert datetime.fromisoformat(again['card']['due']) < datetime.fromisoformat(good['card']['due'])
    assert good['rating'] == 3 and again['rating'] == 1
    tomorrow = NOW + timedelta(days=2)
    later = review(good['card'], 'card_synthetic', True, tomorrow)
    assert datetime.fromisoformat(later['card']['due']) > tomorrow
    assert later['version'].startswith('fsrs-6.3.2')


def test_scheduler_rejects_naive_and_time_reversal():
    from app.learning.scheduler import review
    with pytest.raises(ValueError): review(None, 'test', True, NOW.replace(tzinfo=None))
    first = review(None, 'test', True, NOW)
    with pytest.raises(ValueError): review(first['card'], 'test', True, NOW - timedelta(seconds=1))


def test_bkt_reports_prior_observation_posterior_and_learning_separately():
    from app.learning.knowledge_tracing import update
    yes, no = update(.2, True), update(.2, False)
    assert no['mastery'] < .2 < yes['mastery']
    assert no['posterior'] < no['mastery'] and yes['posterior'] < yes['mastery']
    assert yes['predicted_correct'] == pytest.approx(.38)
    assert yes['version'] == 'bkt-default-v1'
    assert all(0 <= item['mastery'] <= 1 for item in (yes, no))


@pytest.mark.parametrize('prior', [-1, 2, float('nan'), float('inf')])
def test_bkt_rejects_invalid_probabilities(prior):
    from app.learning.knowledge_tracing import update
    with pytest.raises(ValueError): update(prior, True)


def test_concept_mapping_is_document_scoped_and_does_not_merge_unrelated_labels():
    from app.learning.knowledge_tracing import concept_mapping
    q = {'id': 'q1', 'knowledge_point': ' 学习率 ', 'citations': [{'doc_id': 'doc_a'}]}
    one = concept_mapping(q, 'quiz_a')
    assert one['id'] == concept_mapping({**q, 'knowledge_point': '学习率'}, 'quiz_b')['id']
    assert one['id'] != concept_mapping({**q, 'citations': [{'doc_id': 'doc_b'}]}, 'quiz_b')['id']
    assert one['confidence'] == 'quote_linked_not_human_verified'
    assert concept_mapping({**q, 'citations': []}, 'quiz_a')['id'] != concept_mapping({**q, 'citations': []}, 'quiz_b')['id']


@pytest.mark.parametrize('date,hours', [('2026-03-08', 23), ('2026-11-01', 25)])
def test_learning_days_follow_dst_not_fixed_24_hour_windows(date, hours):
    from app.services.learning_state_service import local_day
    start, end = local_day(datetime.fromisoformat(date + 'T18:00:00+00:00'), 'America/New_York')
    assert (end.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds() == hours * 3600


@pytest.mark.parametrize('extra', [{'user_id': 1}, {'is_correct': True}, {'mastery': 1}, {'due_at': 'tomorrow'}, {'version': True}])
def test_review_request_rejects_client_owned_scores_and_schedules(extra):
    from app.services.learning_state_service import ReviewSubmission
    with pytest.raises(ValueError): ReviewSubmission.model_validate({'version': 1, 'selected_answers': ['A'], **extra})
