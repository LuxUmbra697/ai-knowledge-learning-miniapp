# Learning State and Review

## Responsibilities

An authoritative first answer inserts an observation, a review card and an event in the same MySQL
transaction as the answer. An identical replay does not create a second observation. A failed
observation rolls back the answer. Migration 9 adds three owner-scoped tables without changing or
clearing existing answers. Only isolated local schemas have received this migration so far.

- `backend/app/learning/knowledge_tracing.py`: default BKT parameters update the probability estimate
  after each answer. The event records the prior, predicted correctness, posterior, learning step,
  parameter version and observation count. Repeated questions are correlated; the estimate is not
  an exam score or an independently measured learning outcome.
- `backend/app/learning/scheduler.py`: FSRS 6.3.2 default parameters, retention 0.9 and fuzz disabled
  determine the next due date. Correctness maps to Good/Again, not to a claimed measurement of
  recall fluency. No personal parameter training has been performed.
- `backend/app/services/learning_state_service.py`: owns scheduling transactions, review queues,
  favorites, user-confirmed error categories and timezone-aware daily activity.

Knowledge labels are normalized and scoped to their document IDs (or the legacy quiz). Exact source
quotes provide a link, not proof that the model's knowledge-point label is pedagogically correct.
Unverified labels are explicitly distinguished. BKT and FSRS have separate versions and outputs;
they are not combined into an opaque score.

## Review Contract

Each card has a monotonically increasing version. `POST /api/v1/learning/cards/{id}/answer` accepts
only that version, the submitted answer and duration. Server time determines whether it is due.
The server locks the owned card, checks a prior event, grades the stored question and commits the
event, estimate and next schedule together. The same version and answer replay the result; a
different answer or stale version conflicts. Review grants no XP. Owner filtering also applies to
the original quiz and historical result. Unanswered cards contain no solutions or source quotes.

The Taro page saves the account-scoped pending request before sending it. A lost response can be
retried after refresh without a second learning event. A saved result reference retrieves the
already committed event. The browser test deliberately aborts a response **after** the real API
has committed, then reloads and verifies exactly one event.

All stored times are UTC. Daily summaries use IANA timezone boundaries, including DST days that
are 23 or 25 hours. Fourteen-day trends are capped at 5,000 events and disclose truncation.
Due queues currently return up to 50 cards, and the suggested session load is capped at 20.
Favorites and a user-confirmed error label do not change the scheduling version.

## Reproduction and Limits

Run `backend/venv/Scripts/python.exe scripts/test_offline.py -q` and
`backend/venv/Scripts/python.exe scripts/test_database.py -q` from the repository root on Windows;
on Unix substitute `backend/venv/bin/python`. The database runner refuses non-loopback databases
and uses the isolated `ai_learn_test` schema. Its fixture serializes budget-ledger use and restores
prior counters, so repeated tests do not accidentally consume the next test's budget. Production
limits are not disabled. `frontend/e2e/review.spec.ts` runs against the isolated local API with no
external provider calls. Runtime captures are in `docs/screenshots/h5/07-review-plan.png` and 23-25.

Named error notebooks are implemented with explicit collection and versioned mutations. See
`study-maps.md` for derived question/source relationships, which are not prerequisite graphs.
Prerequisite planning, trained personal parameters and evidence of improved retention remain
separately tracked work. Native build success must not be described as native-device verification.

FSRS is the MIT-licensed [open-spaced-repetition/py-fsrs](https://github.com/open-spaced-repetition/py-fsrs)
implementation. BKT here is a small explicit Bayesian update, not a newly trained foundation model.
