# Configurable Practice And Assessment

The shared Taro interface accepts a total of 1-20 questions or an exact per-type blueprint:
single, multiple, judgment, fill-in and written. Selecting a total restores the default three-type
mix; editing individual counts changes the total. Zero-count types are omitted. The server rejects
unknown types, noninteger counts, negative counts, zero totals, totals above 20 and conflicting sums.
Defaults remain compatible with the original five-question interface.

## Generation

`models/quiz.py` validates admission. `learning/quiz_blueprint.py` deterministically divides larger
sets into batches of at most five. `llm/quiz_batches.py` gives each batch a stable structured-stage
name; the existing durable private-practice worker restores saved responses without another paid
call. Each stage permits three attempts including its first call. The shared task budget still
limits total calls, input size, tokens and runtime; a 20-question request is not a guarantee that a
limited account can afford its worst-case retries. Duplicate stems across batches fail publication.

Generated counts, options, answer cardinality, text lengths and difficulty are validated. Private
questions retain exact quotations and server-owned document coordinates. These syntactic/evidence
checks do not establish semantic correctness. Large question sets have deterministic recovery
coverage; the controlled live smoke used five questions, not twenty.

## Authoritative Grading

Choice/judgment answers retain exact server-side option-set grading. Fill-in questions contain
1-4 ordered blanks and up to eight accepted variants per blank. The answer must match a variant
after Unicode NFKC, case folding and whitespace normalization. This is exact matching, not a
semantic evaluator; unlisted correct synonyms can be marked wrong. Original answer order matters.

Written questions contain one reference answer and 1-5 assessment criteria. The `/answer/async`
entry authenticates ownership and normalizes the submitted text before admitting a durable `grade`
task. It does not accept a client verdict. The model checks each rubric item, identifies
contradictions and returns short feedback with exact student quotations. `llm/written_grading.py`
rejects fabricated quotes, missing/duplicate rubric indices and unsupported output fields. An
uncertain model response fails explicitly rather than updating learning state.

The server counts a written answer correct only when every criterion is met and no contradiction
is flagged. This remains a model judgment, not human ground truth. The UI labels its provenance.
The current interface does not provide a teacher appeal/override workflow. Rubric quality and
semantic equivalence require a larger annotated evaluation before grading-accuracy claims.

Answer variants, reference answers, rubric and explanations are excluded before submission.
Only the number of blanks is exposed. The completed attempt reveals its own assessment and source
evidence. Quiz history and review lists use the same private/public serializer.

## Transactions And Recovery

`written_grade_service.py` serializes admission on the owned user row. Concurrent identical
answers reuse an active task, including alternate device request keys; changed answers receive a
conflict. A completed attempt is immutable and replays without another paid call. Cancellation
invalidates the job lease, so a late model result cannot publish.

Publication locks the running job and then the quiz or review card. The attempt, BKT observation,
FSRS state and completed job commit in the same database transaction. The task's public result
contains references, not raw provider checkpoints. A failure of the final job write rolls back all
learning updates. Versioned reviews preserve their original event identity and do not award XP.
An external call interrupted before its outcome is recorded still fails as outcome-unknown; this
is not an exactly-once provider-billing guarantee.

The H5/native shared text controls use Taro components. H5 accessible labels reach the inner
elements through the documented [`nativeProps` adapter](https://docs.taro.zone/docs/components/forms/input).
Drafts and written task request keys are account-namespaced. Leaving a page cancels polling, not the
server job; reopening resumes the saved assessment. Cancellation is also available in task history.

## Reproduction

Run against the isolated services described in `implementation-tracker.md`, never a production DB:

```powershell
backend/venv/Scripts/python.exe scripts/test_offline.py -q
backend/venv/Scripts/python.exe scripts/test_database.py -q
cd frontend
npm run typecheck
npm test
npm run build:h5
npm run build:weapp
npx playwright test e2e/text-practice.spec.ts e2e/quiz-tasks.spec.ts
```

`scripts/smoke_text_quiz.py --paid` requires the private local browser fixture prepared by the M2
live verification. It first verifies every source chunk against the public synthetic fixture,
then allows at most one embedding, three quiz and three written-assessment calls. It does not run
in default CI. The observed run used 3 external calls, reported 2531 tokens and completed both
generation and assessment. Embedding token usage and currency cost were not returned.
The positive answer was the generated reference answer: this is a wiring smoke, not student-data
testing or measured grading accuracy. See `evidence/text-quiz-live.json` and the genuine H5 captures
`screenshots/h5/35-live-written-assessment.png` and `36-live-written-desktop.png`.

## Remaining Boundaries

Public and private text generation and written grading use the durable queue. The original
image-generation path still needs migration to the same task protocol. Native builds are separate
from actual WeChat IDE/device verification, which remains pending. No deployment success is claimed
by local screenshots or model calls. FSRS/BKT use the resulting observations as uncertain proxies,
not verified measures of student knowledge.

## Public Topic Practice

Both text entry points enqueue owned `quiz` jobs; synchronous compatibility requests only wait for
the result. Public requests carry empty document scope and never query the user's private corpus.
The home page persists the exact topic, type counts, search consent and request key before POST.
A lost response is retried using that key. Reopening a completed request does not create another
paid task. Starting another group is explicit and only available after the previous task terminates.

`use_web_search` defaults to false and cannot be combined with `doc_id`. A public request without
search is labelled as model knowledge, not cited evidence. With explicit consent, one Tavily basic
search is reserved in the existing daily/task provider budget, with a 15-second HTTP timeout and
18-second total deadline. It uses at most three results and a 64 KiB response cap; automatic depth,
raw pages, extraction, images, redirects and SDK retries are disabled. Each excerpt is limited to
1000 characters. Failures and no results terminate with an actionable message, not silent fallback.
This replaces the unrestricted ReAct search only for text practice; it is not described as a
multi-agent system. API settings follow the [Tavily search contract](https://docs.tavily.com/documentation/api-reference/endpoint/search).

Migration 12 records the source context atomically with the quiz. Web references remain explicitly
unverified at question level, separate from exact private-document citations. URLs/excerpts are
withheld until all questions are submitted and are shown on the review page. Stored provider
responses are reused after restart. No raw question checkpoints appear in generic task responses.

The controlled 2026-09-15 local run used **2 external calls**, **3253 reported model tokens**, and
**9104 ms** total wait. The search token/currency cost was not returned; there is no zero-cost claim.
The run verified generation, exact three-type quotas, request replay and pre-answer hiding, not
the semantic correctness of each question. `evidence/public-quiz-live.json` records the result.

```powershell
backend/venv/Scripts/python.exe scripts/run_local.py --with-models --with-search --port 18081
# In a second terminal after preparing the private smoke identity fixture:
backend/venv/Scripts/python.exe scripts/smoke_public_quiz.py --paid --web
cd frontend
npm run test:e2e -- public-practice.spec.ts
```

`--with-search` is explicit; the default isolated launcher still disables searches. Credentials
are loaded only from the existing private environment file and never enter frontend artifacts.
