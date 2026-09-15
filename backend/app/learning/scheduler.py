"""Thin FSRS adapter. Objective correctness maps to Again/Good, not subjective fluency."""
from datetime import timezone
import hashlib

from fsrs import Card, Rating, Scheduler

VERSION = 'fsrs-6.3.2-default-v1'
SCHEDULER = Scheduler(desired_retention=.9, maximum_interval=365, enable_fuzzing=False)


def review(previous, card_id, correct, now):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Review time must be timezone aware')
    now = now.astimezone(timezone.utc)
    card = Card.from_dict(previous) if previous else Card(card_id=int(hashlib.sha256(card_id.encode()).hexdigest()[:13], 16), due=now)
    if card.last_review and now < card.last_review:
        raise ValueError('Review time cannot precede its last event')
    rating = Rating.Good if correct else Rating.Again
    result, log = SCHEDULER.review_card(card, rating, review_datetime=now)
    return {'card': result.to_dict(), 'log': log.to_dict(), 'rating': int(rating), 'version': VERSION}
