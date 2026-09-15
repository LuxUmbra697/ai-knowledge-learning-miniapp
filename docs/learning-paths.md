# Learning Paths and Confirmed Plans

This module connects recorded practice with an explicit prerequisite graph and a small learning
plan. It does not infer prerequisite truth from a model prompt or blend scheduling and mastery
into one unexplained score.

## Learner Flow

1. Complete a practice question. Its scoped knowledge-point label receives a BKT observation and
   the question receives an FSRS review date through the existing authoritative grading transaction.
2. In **Learning Paths and Plans**, inspect the proposed reading/review tasks. Choose a 5-60 minute
   session budget and a supported display timezone. Preview has no database-write side effect.
3. Optionally set prerequisite edges between owned, observed concepts. Confirm the change. A loop,
   self-edge, duplicate or unavailable node is rejected. Unconnected nodes remain independent
   topics, not broken references.
4. Confirm a plan. Its original recommendations and their numeric basis are retained. Later graph
   changes and earlier-day plans are explicitly marked; they are not silently rewritten.
5. Open a specific review question from the plan. Only a persisted server review event can complete
   a review item. A reading item can be explicitly checked after viewing the old explanation; that
   checkbox does not increase mastery, XP or review counts.

The page's concept labels come from generated questions and their source mapping. User-confirmed
edges record the learner's intended sequence, not independently labelled educational prerequisites.
The original review maps remain separate: their containment/evidence links are not prerequisite
relations. H5 renders the explicit path through the existing strict Mermaid renderer; native code
uses the existing Dagre/Canvas adapter and full text outline. Native execution is still unverified.

## Deterministic Policy

Implementation: `backend/app/learning/path_planner.py`, version `prerequisite-workload-v1`.
The standard-library `graphlib.TopologicalSorter` supplies cycle detection and topological ordering.
Input nodes and parent lists are sorted for reproducible tie-breaking.

- A prerequisite is considered ready for this policy only after at least **three observations**
  and a default BKT estimate of **0.70**. These are explicit scheduling-policy thresholds, not an
  exam pass mark or calibrated proof of mastery.
- All unmet ancestors block a new recommendation for the dependent concept. The existing manual
  review queue remains accessible; the plan does not lock learners out of their own questions.
- At most the earliest due card for each eligible concept is proposed. Due review has priority
  `4 + min(overdue_days, 7) / 7 + (1 - mastery)`.
- A not-yet-due concept with insufficient observations or a low estimate may receive a reading
  task, priority `2 * (1 - mastery) + 0.5` when it supports another blocked concept, otherwise
  `2 * (1 - mastery)`. This does not bring its FSRS review date forward.
- Review uses an estimated three minutes, reading two minutes. Greedy priority selection retains
  at most ten items and never exceeds the requested session budget. Time estimates are policy
  constants, not actual measured attention, model latency or exam performance.
- There is no suitable question on a brand-new account, so the preview is empty. The app directs
  the learner to acquire an actual practice record instead of displaying invented mastery.

Snapshot scope is limited to 100 concepts and 500 owned cards. Concepts already used by explicit
edges are retained first, then lower-estimate concepts. Cards are ordered by due time and ID.
Truncation is exposed; the result is not advertised as a complete global optimization. There are
at most 180 edges. The topological text outline retains disconnected topics.

## Persistence and Concurrency

Migration 15 adds `learning_path_settings`, `learning_plans` and `learning_plan_checks`, each with
owner foreign keys. It has been applied only to isolated local/test schemas at this checkpoint.

The settings update checks an optimistic version while holding the account row. A preview's
SHA-256 fingerprint covers its date, timezone, graph version, selected learning state, current card
versions/dates and proposed policy output. It excludes the changing display timestamp. Confirmation
recomputes this fingerprint in a consistent database snapshot. Changed observations, graph or day
produce a conflict and require a new preview. A subsequent learning event can of course occur
after confirmation; the plan remains an honest snapshot, not a permanent lock on learning.

Confirmation binds an owner-scoped request key to a canonical request hash. Replays return the
same immutable plan; changed bodies with the same key conflict. The UI derives the key from the
preview fingerprint, including across refresh or a lost response. Confirmations are limited to
20 per user per UTC day; the latest 20 plans are listed. This limit is separate from the learner's
display timezone. Older persisted plans remain accessible by their owned ID.

Review completion is computed from `learning_events`, requiring source `review` and an event
version at least as new as the plan's card version. Manual completion of a review returns 422.
Reading confirmation is separately labelled `user_read_confirmation`; repeated checks are
idempotent. Plan/check writes never update `learning_concepts`, `learning_cards` or user XP.

## Endpoints and Verification

All endpoints require the existing JWT and derive the user from it:

| Endpoint under `/api/v1/learning` | Responsibility |
| --- | --- |
| `GET /path`, `PUT /path` | Owned concepts and versioned prerequisite edges |
| `GET /plans/preview?minutes=15&timezone=Asia/Shanghai` | Read-only deterministic proposal |
| `POST /plans` with `Idempotency-Key` | Explicit fingerprint-checked confirmation |
| `GET /plans`, `GET /plans/{id}` | Owned history and actual completion state |
| `PUT /plans/{id}/read/{item}` | Explicit reading-only checklist entry |
| `GET /cards/{id}` | Answer-hidden owned question for direct review navigation |

Executed commands from the repository root, with isolated MySQL and API already running:

```powershell
backend/venv/Scripts/python.exe scripts/test_offline.py -q -k 'dag_rejects or plan_balances or not_due_study or plan_commands'
backend/venv/Scripts/python.exe scripts/test_database.py -k 'plan_confirmation or read_checks'
cd frontend
npx playwright test e2e/planning.spec.ts e2e/planning-reading.spec.ts
```

Deterministic tests cover cycle/self/duplicate/dangling nodes, transitive prerequisites, bounded
workload, overdue preference, cold start, explicit consent, unbounded input and separate reading
semantics. Real isolated MySQL cases cover cross-owner rejection, concurrent confirmation,
idempotency, stale snapshots, actual review events, graph version conflicts and timezone dates.

Real Chromium workflows use explicitly synthetic historical attempts and zero provider calls.
They exercise the home entry, preview/cancel/confirm, direct question navigation, actual grading,
persisted completion, graph editing, cycle rejection, Mermaid image decoding, plan history,
reading confirmation and unchanged scheduling/mastery. Viewports: 320, 390 and 1440 px.

Evidence: [plan workflow](evidence/learning-plans-ui.json), [reading checklist](evidence/plan-reading-ui.json),
[confirmed plan screenshot](screenshots/h5/48-confirmed-study-plan.png),
[actual prerequisite graph](screenshots/h5/49-prerequisite-path.png),
[reading confirmation](screenshots/h5/50-confirmed-reading.png).

The separate [BKT fitting experiment](algorithm-experiments.md) proves a reproducible synthetic
training/evaluation pipeline. It neither trains this ranking policy nor establishes real student
learning improvement. Paid model integration belongs to tutoring, generation and rubric grading;
planning itself deliberately makes no external model call.
