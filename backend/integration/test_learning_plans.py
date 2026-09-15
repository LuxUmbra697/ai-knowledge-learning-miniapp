import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from test_learning_state import fixture

from app.services import learning_state_service as learning
from app.services.grading_service import AnswerSubmission, submit_question


@pytest.mark.asyncio
async def test_plan_confirmation_is_owned_idempotent_stale_safe_and_review_driven(users, monkeypatch):
    from app.models.learning_path import PathUpdate, PlanConfirm
    from app.services import learning_path_service as plans
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(learning, 'utcnow', lambda: now - timedelta(days=2))
    for _ in range(2):
        quiz = await fixture(users[0])
        await submit_question(quiz, users[0], AnswerSubmission(question_id='q1', selected_answers=['B']))
    monkeypatch.setattr(learning, 'utcnow', lambda: now)
    monkeypatch.setattr(plans, 'utcnow', lambda: now)
    before = await learning.summary(users[0])
    preview = await plans.preview(users[0], 15, 'Asia/Shanghai')
    assert len(preview['items']) == 2 and await plans.list_plans(users[0]) == []
    request = PlanConfirm(fingerprint=preview['fingerprint'], minutes=15, confirmed=True)
    a, b = await asyncio.gather(*[plans.confirm(users[0], request, 'plan_confirm_fixture') for _ in range(2)])
    assert a['plan_id'] == b['plan_id'] and len(await plans.list_plans(users[0])) == 1
    with pytest.raises(HTTPException) as denied:
        await plans.detail(a['plan_id'], users[1])
    assert denied.value.status_code == 404
    card = preview['items'][0]
    with pytest.raises(HTTPException) as invalid:
        await plans.mark_read(a['plan_id'], users[0], card['id'])
    assert invalid.value.status_code == 422
    assert (await learning.summary(users[0]))['concepts'] == before['concepts']
    await learning.submit_review(card['card_id'], users[0], learning.ReviewSubmission(version=card['card_version'], selected_answers=['A']))
    current = await plans.detail(a['plan_id'], users[0])
    assert next(item for item in current['items'] if item['id'] == card['id'])['completion_source'] == 'server_review_event'
    with pytest.raises(HTTPException) as stale:
        await plans.confirm(users[0], request, 'plan_stale_fixture')
    assert stale.value.status_code == 409
    ids = [node['concept_id'] for node in preview['concepts']]
    changed = await plans.update_path(users[0], PathUpdate(version=0, edges=[(ids[0], ids[1])]))
    assert changed['version'] == 1
    assert (await plans.detail(a['plan_id'], users[0]))['path_changed']
    with pytest.raises(HTTPException) as conflict:
        await plans.update_path(users[0], PathUpdate(version=0, edges=[]))
    assert conflict.value.status_code == 409
    for owner, edges in [(users[1], [(ids[0], ids[1])]), (users[0], [(ids[0], ids[1]), (ids[1], ids[0])])]:
        with pytest.raises(HTTPException):
            await plans.update_path(owner, PathUpdate(version=0 if owner == users[1] else 1, edges=edges))


@pytest.mark.asyncio
async def test_read_checks_are_explicit_and_never_change_mastery_or_schedule(users, monkeypatch):
    from app.models.learning_path import PlanConfirm
    from app.services import learning_path_service as plans
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(learning, 'utcnow', lambda: now)
    monkeypatch.setattr(plans, 'utcnow', lambda: now)
    quiz = await fixture(users[0])
    await submit_question(quiz, users[0], AnswerSubmission(question_id='q1', selected_answers=['B']))
    before = await learning.cards(users[0], 'all')
    preview = await plans.preview(users[0], 5, 'America/New_York')
    assert preview['day'] == '2026-09-14' and preview['items'][0]['kind'] == 'read'
    created = await plans.confirm(users[0], PlanConfirm(fingerprint=preview['fingerprint'], minutes=5, timezone='America/New_York', confirmed=True), 'read_confirm_fixture')
    item = preview['items'][0]
    for _ in range(2):
        await plans.mark_read(created['plan_id'], users[0], item['id'])
    assert (await plans.detail(created['plan_id'], users[0]))['items'][0]['completion_source'] == 'user_read_confirmation'
    assert await learning.cards(users[0], 'all') == before
    with pytest.raises(HTTPException):
        await plans.mark_read(created['plan_id'], users[1], item['id'])
    with pytest.raises(HTTPException):
        await plans.preview(users[0], 15, 'Invalid/Zone')
