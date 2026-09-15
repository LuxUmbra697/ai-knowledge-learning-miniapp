"""Real isolated MySQL: authoritative learning updates, versioned reviews and ownership."""
from datetime import datetime, timedelta, timezone
import uuid

import pytest
from fastapi import HTTPException

from app.repositories import quiz_repository
from app.repositories.rag_index_repository import transaction
from app.services.grading_service import AnswerSubmission, submit_question


async def fixture(user):
    quiz_id = 'quiz_' + uuid.uuid4().hex
    question = dict(id='q1', type='single', stem='Synthetic recovery question',
        options=[dict(key='A', text='Save'), dict(key='B', text='Forget')], answer=['A'],
        explanation='Synthetic fixture only.', knowledge_point='Recovery', difficulty='easy')
    await quiz_repository.save_quiz_session(quiz_id, user, 'Synthetic', 'Synthetic', 'Synthetic', [question])
    return quiz_id


@pytest.mark.asyncio
async def test_initial_answer_and_review_are_atomic_idempotent_and_owner_scoped(users, monkeypatch):
    from app.services import learning_state_service as service
    now = datetime(2026, 9, 14, 15, 55, tzinfo=timezone.utc)
    monkeypatch.setattr(service, 'utcnow', lambda: now)
    quiz = await fixture(users[0])
    submission = AnswerSubmission(question_id='q1', selected_answers=['B'])
    await submit_question(quiz, users[0], submission)
    await submit_question(quiz, users[0], submission)
    summary = await service.summary(users[0], 'Asia/Shanghai')
    assert summary['concepts'][0]['attempts'] == 1 and summary['total_cards'] == 1
    assert summary['today_answers'] == 1 and summary['due_count'] == 0
    cards = await service.cards(users[0], 'wrong')
    card = cards[0]
    assert 'answer' not in card['question'] and card['version'] == 1
    assert await service.cards(users[1], 'all') == []
    req = service.ReviewSubmission(version=1, selected_answers=['A'])
    with pytest.raises(HTTPException) as error:
        await service.submit_review(card['card_id'], users[1], req)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        await service.submit_review(card['card_id'], users[0], req)
    assert error.value.status_code == 409
    monkeypatch.setattr(service, 'utcnow', lambda: now + timedelta(minutes=11))
    result = await service.submit_review(card['card_id'], users[0], req)
    assert result['record']['is_correct'] and result['version'] == 2
    restored = await service.review_result(card['card_id'], 1, users[0])
    assert restored['record'] == result['record'] and restored['question']['answer'] == ['A']
    with pytest.raises(HTTPException) as error:
        await service.review_result(card['card_id'], 1, users[1])
    assert error.value.status_code == 404
    assert (await service.submit_review(card['card_id'], users[0], req))['replayed']
    with pytest.raises(HTTPException) as error:
        await service.submit_review(card['card_id'], users[0], service.ReviewSubmission(version=1, selected_answers=['B']))
    assert error.value.status_code == 409
    after = await service.summary(users[0], 'Asia/Shanghai')
    assert after['today_answers'] == 0 and after['concepts'][0]['attempts'] == 2
    assert after['today_reviews'] == 1
    async with transaction() as cur:
        await cur.execute('SELECT total_xp FROM users WHERE id=%s', (users[0],))
        assert (await cur.fetchone())['total_xp'] == 0


@pytest.mark.asyncio
async def test_learning_write_failure_rolls_back_the_answer(users, monkeypatch):
    from app.services import learning_state_service as service
    quiz = await fixture(users[0])
    async def fail(*args): raise RuntimeError('Synthetic state write failure')
    monkeypatch.setattr(service, 'record_initial', fail)
    with pytest.raises(RuntimeError):
        await submit_question(quiz, users[0], AnswerSubmission(question_id='q1', selected_answers=['A']))
    async with transaction() as cur:
        await cur.execute('SELECT COUNT(*) AS n FROM quiz_question_attempts WHERE quiz_id=%s', (quiz,))
        assert (await cur.fetchone())['n'] == 0


@pytest.mark.asyncio
async def test_favorites_and_confirmed_causes_cannot_cross_users(users):
    from app.services import learning_state_service as service
    quiz = await fixture(users[0])
    await submit_question(quiz, users[0], AnswerSubmission(question_id='q1', selected_answers=['B']))
    card = (await service.cards(users[0], 'wrong'))[0]
    patch = service.CardSettings(favorite=True, diagnosis='concept_confusion')
    with pytest.raises(HTTPException) as error:
        await service.update_card(card['card_id'], users[1], patch)
    assert error.value.status_code == 404
    await service.update_card(card['card_id'], users[0], patch)
    await service.update_card(card['card_id'], users[0], patch)
    saved = (await service.cards(users[0], 'favorites'))[0]
    assert saved['favorite'] and saved['diagnosis'] == 'concept_confusion' and saved['version'] == 1
