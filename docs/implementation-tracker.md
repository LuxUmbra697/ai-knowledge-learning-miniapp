# Implementation and Verification Ledger

Started: 2026-09-11 (Asia/Shanghai). Initial revision: `148970c`.
This ledger records observed results; planned capabilities are not delivery claims.

## Stages

| Stage | Acceptance | State | Evidence |
| --- | --- | --- | --- |
| M0 | Isolated baseline; authenticated ownership; authoritative grading; safe config | Core checks passed; release hardening continues | `evidence/m0-local.json`; 159 deterministic tests |
| M1 | Taro H5/weapp, separate outputs, independent login, five themes | H5 core flow passed; native runtime gate pending | `frontend/e2e`; `screenshots/h5`; DevTools service port unavailable |
| M2 | Bounded parsing, scoped hybrid retrieval, citations, 100-case evaluation | Retrieval/citation checkpoint verified; remaining gates below | 104 synthetic cases; real index and answer evidence; dual builds |
| M3 | Bounded learning agent, durable worker, cancellation/recovery | Index, retrieval, answer, report and private text practice verified; public-topic/image migration and tutoring graph pending | MySQL recovery/cancellation tests, real model tasks and H5 history |
| M4 | Mastery, FSRS, prerequisites, reproducible offline experiment | Pending | No implementation yet |
| M5 | Browser and DevTools workflows, screenshots, regression | In progress alongside each module | Actual H5 screenshots exist; no weapp screenshots claimed |
| M6 | New deployment plus all existing sites healthy | Pending | No gateway mutations |
| M7 | Bilingual README, documentation, private handoff, GitHub and CI | Pending | Remote history verified |

## Initial Audit Findings

This table preserves the initial observations. Current completion and requirement-to-code/test/evidence
mapping are recorded in the stage table and executed checkpoints below.

| Requirement | Existing implementation | Finding / next change | Regression / evidence |
| --- | --- | --- | --- |
| Config and production DB protection | `backend/app/core/config.py`, `core/db.py` | CWD-dependent dotenv; startup creates database/tables | Isolated settings and explicit migrations required |
| Authentication | `core/auth.py`, `services/user_service.py` | Real WeChat code exchange exists; H5 has no account login | New/expired/cross-user API cases required |
| Task isolation | `api/v1/routes/quiz.py`, `repositories/task_repository.py` | Task GET unauthenticated and unscoped | Reproduce before repair |
| Scoring | `services/report_service.py`, `scoring_service.py` | Trusts client correctness/questions; repeat XP not atomic | Forged correctness and repeat submission cases required |
| Answer disclosure | `models/quiz.py`, `services/history_service.py` | Generation/history returns answers before submission | Public/private question serializers required |
| Durability | `services/quiz_service.py`, `knowledge_service.py` | DB status exists; execution uses process tasks without recovery | Restart and cancellation cases required |
| Retrieval | `vector_store_service.py`, `rag_service.py` | Per-user Chroma and doc filter exist; final text loses evidence | Dense baseline, RRF, citation validation required |
| Upload | `document_loader_service.py`, `knowledge_service.py` | PDF/DOCX/MD/TXT; no OCR; synchronous parse blocks async worker | Limits, signatures, duplicate/delete races required |
| Dual platform | `frontend/config`, `src/app.ts` | Shared dist, root publicPath, example API, unconditional Taro.login | Sequential builds and real navigation required |
| Polling | `frontend/src/services/api.ts` | Async setInterval can overlap requests | Slow request and cancellation tests required |
| Privacy | `.gitignore`, `.dockerignore` | Blanket docs/.github ignored | Exact legacy private files excluded; public docs allowed |
| Deployment | No verified new service | Existing gateways must be inventoried before mutation | Read-only server/HTTPS audit pending |

## Baseline

- Working tree was clean; branch `main`; five existing commits.
- Specified GitHub repository HEAD matches local `148970c`. Local origin uses the former repository name; no remote history was overwritten.
- Taro 4.1.11, React 18, Node 22.19.0. Existing Python venv reports 3.13.9 but has no pytest or backend libraries. Initial backend test command failed at missing pytest before application import.
- Existing real dotenv located at `backend/.env`; no secrets copied to documentation. Startup has not been run against that database.
- Docker CLI is installed; Docker engine is not running. Two local MySQL processes exist; their data will not be reused for tests.
- WeChat DevTools 2.01.2510280 is installed and running. Login, automation and account capabilities not yet verified.

## M0 Executed Loop

- Added nine failing authorization regressions, repaired task owner filtering and JWT required identity validation; all nine passed.
- Added grading/cardinality and non-mutating startup checks. Startup now opens a connection without schema creation; migrations run explicitly.
- Answers/explanations are removed from generated practice and unrevealed history. Each answer is submitted to the server; cross-device retries lock the quiz row and reuse the first result. Changed answers receive 409.
- Report generation reads stored questions and submitted records. Report, score and XP commit together; repeat completion cannot award XP again. Model generation still needs the durable budgeted task work in M3 to prevent concurrent duplicate model charges.
- Rotated the target's weak, publicly guessable JWT value with a private backup. No provider key was changed. Re-scanning the five existing revisions against current secrets found zero matches. No history rewrite occurred.
- H5 and weapp baseline builds succeeded, but the second build overwrote the first. H5 initial entry: 357 KiB, a measured webpack warning. TypeScript check passed after grading integration.
- Original test run: 125 passed, 14 setup errors due to Windows temporary directory permissions. A repository-private temporary directory fixed the environment issue. Updated full regression: **159 passed**, one upstream LangGraph deprecation warning, 7.50 seconds. No tests removed.
- Real HTTP against a running API and isolated MySQL 8.0.45: **11 checks passed**, including five concurrent answer submissions and three report transactions. Zero external model calls. This is not browser or production evidence.
- Existing cloud MySQL connection works; the configured schema does not exist. Database selection awaits owner clarification. No cloud DDL or data write performed.
- Server inventory: Ubuntu 22.04.5, 2 CPUs, 1608 MiB memory visible, approximately 289-299 MiB available, 40 GiB filesystem with 28 GiB free. Existing services stay running. Deployment capacity must be measured before starting the new workload.
- Gateway configuration and certificate metadata inspected read-only. Certificate covers the configured domain and expires 2026-12-02. Renewal automation and public TLS chain still need verification.
- WeChat CLI activation timed out; manual service-port activation requested. No DevTools screenshot or real-device success claimed.

Pending M0 release gates: bounded uploads and fail-closed persistence, durable cost limits, security headers, production JWT validation, migration/backup rehearsal against the selected cloud schema.

## M1 Executed Loop

- Added independent username/password H5 accounts with scrypt, salted hashes and persisted rate limits. WeChat identity exchange remains separate; no fabricated OpenID or automatic cross-platform merge.
- Added five appearance themes, two original generated companion forms and three poses per form. Frames are 144 KiB combined. Dragging uses pointer events only in `.h5.tsx`; mini-program uses native `MovableView`. Reduced-motion, input focus, page hiding, resize, edge docking and collision checks are explicit.
- Added the missing H5 HTML template. The pre-existing H5 build could succeed without producing an entry page; the first browser run reproduced this. An artifact check now requires the entry and `/ai-learn/` asset prefix.
- Separate `dist/h5` and `dist/weapp` outputs now survive consecutive builds. `project.config.json` points to `dist/weapp`. Runtime browser tests use a loopback preview proxy with an independent API location, not a production availability claim.
- Replaced overlapping interval polling with awaited requests and cancellable timers/transport; five frontend unit tests cover bounds, collision, slow requests, cancellation and attempt limits.
- Reworked the existing Taro home/library/profile/practice/report pages. Practice URLs carry only the quiz ID; server records restore submitted questions and per-user local drafts restore unfinished selections. Removed the nonfunctional poster action and fabricated local XP increments.
- Real browser registration and reload, five themes, 320/390/1440 widths, form/pose changes, animation pixel differences, drag persistence and motion settings passed. Tests additionally walk single-choice, multiple-choice and judgment questions through the real API and isolated MySQL, including previous/next navigation, reload recovery and cross-user 404.
- Screenshot inspection reproduced cropped Taro image positioning, invisible secondary-button labels and night-mode textarea backgrounds. Targeted layout assertions and explicit inner-element styles corrected them. Text-safe companion docking and the final associated browser regression passed.
- History ownership already withheld data, but returned HTTP 200 for missing/unowned records. Added a failing test, changed to HTTP 404 with the existing error envelope, and strengthened the legacy test to require no response data.
- These browser fixtures are explicitly synthetic and make zero external model calls. No real-device, WeChat automation, public deployment, RAG quality or algorithm effectiveness result is implied.
- Checkpoint results: 165 backend tests, five frontend unit tests, two multi-step real browser tests. Latest H5 entry gzip is about 115 KiB; both complete build footprints are recorded in `evidence/m1-build-size.json`. This is not a page-load latency or concurrency measurement.
- M1 remaining gates: full native runtime after DevTools access; mobile keyboard/device behavior; subpackage review as more pages are added; avatar upload persistence; all later feature pages and end-to-end evidence.

## M2 Parser Loop (In Progress)

- Added 11 initially failing boundary cases, then expanded to 13 with an actual isolated parser process and timeout handling. New metadata includes content/document SHA-256, parser version, stable chunk ID, chunk offset and one-based PDF pages or DOCX/Markdown sections.
- Preserved real PDF/DOCX/TXT/Markdown processing while replacing two loader-mock dispatch checks with stronger tests extracting real generated PDF streams and DOCX paragraph XML. DOCX XML uses `defusedxml`; archive members are inspected without extracting them to arbitrary paths.
- The API bounds multipart buffering before framework parsing, limits two simultaneous uploads and imposes receive timeouts. Per-file size and path/signature checks precede task creation. These limits are not a throughput claim.
- Parsing executes in a short-lived subprocess with a hard elapsed timeout. Linux has an address-space and CPU limit; the Windows smoke only verifies elapsed-time termination and normal subprocess execution. OCR is explicitly unsupported.
- Real browser file-picker upload of a damaged PDF reaches the API, persists the parser failure in isolated MySQL and preserves the error after refresh. Screenshot: `screenshots/h5/03-upload-feedback.png`.
- Exactly two external smoke calls were made using existing credentials: DeepSeek chat (12 total tokens) and DashScope embedding (18 tokens, 1024 dimensions). Actual results are in `evidence/provider-smoke.json`; billed currency was not queried and is not invented.
- Full deterministic regression: 182 passed, one upstream warning. Hybrid ranking, owned chunk persistence, deletion/index races, retrieval evaluation and successful real embedding/index integration remain to implement before M2 is complete.

## M2 Retrieval and Citation Checkpoint

- Added `kb_index_meta` and `kb_chunks` in explicit migration 3; migrated only the isolated local schema. User-row locking makes duplicate detection and document quota checks atomic. SQL publication checks owner, active state, index fingerprint and revision.
- Chroma remains the vector database, with separate user/index-version collections. Stable vector IDs make identical indexing an upsert; old revision cleanup cannot delete the current revision. SQL tombstones revoke access before physical cleanup, and failed cleanup remains recorded. Deleted sources cannot pass the owned corpus read or citation API.
- `retrieval_service` authorizes the entire document scope before dense/BM25/reranker input. Chinese bigram BM25 and dense ranks combine through RRF; the optional reranker is a bounded lexical rule, not a trained neural model. Provider errors are distinguished from empty evidence.
- `grounded_answer_service` accepts only schema-validated statements with exact source excerpts, limits output/elapsed time and attempts to three including the first, disables SDK retry, and revalidates source access after generation. Private retrieval no longer supplies Tavily tools or returns only the Agent's last string. Public topic search is separate and still requires M3 security review.
- Real local API/MySQL/Chroma: six multi-step checks passed with at most four embedding requests. Cross-user document GET, source GET, retrieval and deletion all returned 404; forged identity fields returned 422. Reindex invalidated prior revision citations. See `evidence/m2-live-index.json`.
- New Taro learning subpackage contains the assistant and original-source pages. H5 browser exercised actual model answers, source navigation and direct refresh. Two browser iterations caught test locator ambiguity due to retained Taro pages; a third passed. A mobile response-scroll regression was corrected and verified. Screenshots are actual runtime captures, not image-generation mockups.
- Real answer evidence: one successful measured request used 553 tokens and produced three source-validated citations. The two earlier UI-debug runs also made bounded real model calls; they are not counted as passed E2E runs. Default E2E excludes the paid test unless explicitly opted in.
- Reproducible evaluation: 104 synthetic rule-labeled queries, 56 chunks, topic-separated partitions, cached real embeddings and actual local Chroma. Acquisition used 15 requests / 2437 tokens. Dense MRR 0.950000, hybrid and lexical-reranked MRR 0.929167; no improvement claim. Raw records and limitations are in `eval/rag` and `rag-evaluation.md`.
- Latest dual artifact check passed. H5 entry gzip: 118521 bytes. Weapp main: 556427 bytes; learning subpackage: 11455 bytes. This verifies artifacts, not native execution. TypeScript and five frontend units passed; default browser suite passed three cases and explicitly skipped the paid case. Pyflakes static checks passed; broader inherited style diagnostics remain for the CI/configuration phase.
- The old loopback DB port became unavailable with Windows bind error 10013; an isolated alternate port was selected without changing firewalls, existing MySQL instances or cloud configuration. Existing test data was retained.

M2 remaining gates: durable indexing/recovery and cleanup worker (M3), a configurable remote reranker only if justified by evaluation/budget, larger independently reviewed relevance/answer data, model-level no-answer/conflict/injection regressions, native WeChat runtime, real PDF/DOCX provider/browser upload beyond deterministic parsing fixtures. Windows parser memory isolation remains weaker than Linux.

### Updated Requirement Evidence

| ID / behavior | Implementation | Tests | Evidence |
| --- | --- | --- | --- |
| RAG-01 bounded document parsing | `services/document_loader_service.py`, `isolated_parser.py`, `core/upload_limits.py` | `test_document_boundaries.py`, `test_upload_limits.py` | H5 `03-upload-feedback.png` |
| RAG-02 owned hybrid recall | `services/retrieval_service.py`, `hybrid_ranking.py` | `test_retrieval_service.py`, `test_hybrid_ranking.py` | `eval/rag/raw-v1.jsonl` |
| RAG-03 duplicate, reindex, deletion | `repositories/rag_index_repository.py`, migration 3 | `integration/test_index_lifecycle.py`, `test_vector_store_service.py` | `evidence/m2-live-index.json` |
| RAG-04 source-located answers | `services/grounded_answer_service.py`, `models/evidence.py`, Taro `learning` package | `test_grounded_answer.py`, `grounded-live.spec.ts` | H5 `04-grounded-chat.png`, `12-source-evidence.png` |
| RAG-05 reproducible evaluation | `scripts/build_rag_dataset.py`, `embed_rag_dataset.py`, `evaluate_rag.py` | `test_rag_dataset.py` | `eval/rag/results-v1.json` |

## M3 Durable Task Checkpoint

- Migrations 4-6 add the owned `learning_jobs` queue, document-to-task link and daily provider budget. Only the isolated local schemas were migrated. Neither cloud MySQL nor existing production applications were modified.
- Upload reserves a staging job and document in one transaction, writes the private file, then activates the job. Maintenance can recover a completed staging file by checking its hash. Publication of SQL chunks, ready status and the completed index task shares one transaction.
- Worker claims use short MySQL 5.7-compatible locking transactions, a 40-second lease, an 8-second heartbeat and a random fencing token. Cancellation wins over late completion. An expired owner cannot publish or mark a replacement worker's document failed.
- A real child worker process was started, terminated after its checkpoint, and replaced by another process that recovered the MySQL checkpoint with zero external calls. A crash while an external request is pending instead produces `external_outcome_unknown`; no automatic repeat of the possibly billed call occurs.
- Per-stage attempts are at most three, task calls at most 12, known tokens at most 20,000 before the next call, cumulative input at most 60,000 UTF-8 bytes, and execution eligibility at most 180 seconds after first claim. One answer has a separate 55-second generation bound. Token limits are pre-call guards, not an exact provider billing cap.
- Daily UTC site admission limits default to 100 provider requests and 500,000 UTF-8 input bytes on the new queue paths. A concurrent two-user test verifies that only one can consume the last available request. SDK retries are disabled on the new private retrieval/answer paths. Legacy quiz/report/image/search paths are not yet covered by this budget and remain release blockers.
- Explicit source retrieval and knowledge answers now run as owned jobs. The compatibility synchronous endpoints wait on those same jobs, rather than launching an independent model call. Document revisions are captured at admission, checked again before execution, and checked when restoring evidence. Task lists omit answer bodies; owned task reads invalidate deleted-source answers.
- H5 and weapp share the task monitor and awaited polling. The assistant saves an account-namespaced task reference and idempotency key. Page hiding stops transport; explicit cancellation changes the server state. Task history uses real stages, trace IDs, observed call counts and checkpoint-interval timings, without private model reasoning.
- Reproduced and fixed: pending-call tasks incorrectly accepted as completed; document deletion cleaning only the current index version; early clearing of cleanup flags while a cancelled native thread could still finish; polling cancellation accessing an uninitialized timer; document-specific assistant refresh failing to restore its task. A cleanup sweep waits beyond the cancelled lease, plus a 60-second grace period, to catch late vector writes.
- First real answer run completed in the backend but exposed the refresh bug. A reuse-only browser pass verified the fix without new provider requests. A subsequent full new-task pass verified idempotent replay, refresh recovery and source navigation: two external calls, 555 returned chat tokens, three validated citations, 5870.44 ms answer-service duration. This includes provider latency but not the entire user journey. See `evidence/m3-live-answer.json` and `evidence/m3-answer-resume.json`.
- One browser attempt started before the restarted API was listening and failed before making any model request. E2E now checks actual loopback API readiness before starting scenarios. It does not hide UI/network failures inside scenarios.
- Real durable upload/index/retrieval/rebuild/delete verification passed seven checks in 10.29 seconds, using four small embedding requests and no chat calls. See `evidence/m3-live-index.json`. Embedding usage is not returned by the current LangChain bridge, so these calls are marked unmetered rather than assigned invented token/currency values.
- Checkpoint regression: 211 deterministic backend tests, 15 isolated MySQL integration tests, seven frontend unit tests and TypeScript checks passed. Task cancellation and damaged-upload browser scenarios passed; real grounded answer/recovery scenarios passed separately. Final artifact and full browser regression results are recorded with this checkpoint's evidence.
- Final staged review reproduced three additional boundaries: duplicate provider-result publication, timeout failures losing vector cleanup grace, and cancellation of a completed answer returning deleted-source evidence. All three received failing tests and fixes; the 15-case database regression passed afterward.
- An options-only offline test invocation accidentally collected the separate database integration directory. Its strict database guard rejected all nine fixtures before any connection. The runner now always targets `backend/tests`; the independent database command remains mandatory and all its assertions remain in place.

M3 still required: migrate legacy quiz/report generation and its image/search calls to the bounded queue; validate structured practice outputs and coverage; implement the learning state graph, Socratic mode and diagnosis; strengthen provider error and cancellation matrices; complete old-task reconciliation and retired-index cleanup; verify the native task UI. No complete learning-Agent or production release claim is made at this checkpoint.

| ID / behavior | Implementation | Tests | Evidence |
| --- | --- | --- | --- |
| JOB-01 owned idempotency and lease fencing | `repositories/job_repository.py`, migrations 4-6 | `integration/test_job_lifecycle.py` | Real MySQL tests and worker child-process restart |
| JOB-02 durable document publication and deletion | `knowledge_service.py`, `rag_index_repository.py`, `job_handlers.py` | `test_knowledge_service.py`, database lifecycle tests | `evidence/m3-live-index.json` |
| JOB-03 persisted answer/retrieval budgets | `learning_task_service.py`, `grounded_answer_service.py`, `retrieval_service.py` | `test_learning_tasks.py`, `test_grounded_answer.py`, global-budget race test | `evidence/m3-live-answer.json` |
| JOB-04 task monitor, cancel and refresh | Taro `learning/tasks`, `learning/assistant`, `services/polling.ts` | `tasks.spec.ts`, `grounded-live.spec.ts`, `answerSession.test.ts` | H5 `13-task-history.png`, `04-grounded-chat.png` |

## M3 Practice Validation Loop

- Added a shared structured-output stage for quiz and report generation: at most three combined transport/format attempts, SDK retries disabled, bounded output and repair feedback without original private inputs. Permanent 4xx (including 429) fail immediately. Redacted logs record stage, attempt, elapsed time, returned tokens and finish reason.
- Quiz validation now checks exact count, all three supported types, distinct IDs/stems/options, submission-compatible ID lengths, answer cardinality and membership, judgment option semantics, display limits, requested difficulty, nonempty knowledge points and server-only image URLs. It does not prove factual correctness or evidence coverage; those remain separate gates.
- Reports reject knowledge points outside the submitted quiz, enforce summary/advice structure, and use the server's score. Mastery and error diagnosis still need the explicit learning algorithm in M4.
- Initially failing regressions reproduced successful responses after failed persistence, five write functions silently succeeding without a connection pool, and malformed-but-parseable exercises. Writes now fail closed. The successful API unit test explicitly mocks and asserts persistence instead of relying on the former silent no-op.
- Actual H5 library -> five real generated questions -> server submissions -> model report -> refresh -> report replay passed. The three question types were all present; answer fields were absent before submission; server score was 20% for this deliberately mechanical fixture, and XP increased by 12 exactly once. A second account received 404 for the report. See `evidence/m3-practice-live.json` and actual screenshot `screenshots/h5/08-learning-report.png`.
- Measured calls: quiz 1 / 1644 tokens / 3679 ms; report 1 / 1441 tokens / 1900 ms. These are model-stage timings, not browser journey latency. Embedding tokens and currency were not measured. The provider evidence file makes that distinction explicit.
- After adding ID/option guards, `scripts/verify_saved_practice.py` revalidated the saved real output and its grading without a provider call. The API was restarted with provider keys disabled, and the saved-report browser recovery test passed without new calls or XP. Only the local fixture database was used; no cloud or production data changed.
- Latest backend deterministic suite: 240 passed. Isolated database suite: 15 passed. Static Pyflakes checks passed. Native WeChat execution and migration of legacy quiz/report tasks into the durable budgeted queue remain pending; this checkpoint does not claim them complete.

| ID / behavior | Implementation | Tests | Evidence |
| --- | --- | --- | --- |
| QUIZ-02 validate usable question contracts | `llm/quiz_chain.py`, `llm/structured_stage.py` | `test_quiz_output_safety.py`, `test_structured_stage.py` | `evidence/m3-practice-live.json` |
| QUIZ-03 fail closed on persistence errors | `repositories/quiz_repository.py`, `task_repository.py`, `services/quiz_service.py` | five missing-pool tests, sync/async failure tests | 240-test offline regression |
| REPORT-02 real generated report and replay | `llm/report_chain.py`, `services/report_service.py` | `practice-live.spec.ts`, `scripts/verify_saved_practice.py` | H5 `08-learning-report.png`, provider usage JSON |

## M3 Durable Report Loop

- Reports now use the existing MySQL queue and controlled worker, including the synchronous compatibility endpoint. Admission reads the owned quiz and authoritative attempt IDs; request-supplied topic/questions/answers never become task payload. Already stored legacy reports remain readable even when the old record predates per-question attempts.
- Active reports coalesce by owned payload across devices and different request keys. Completed immutable reports also reuse their completed task; explicit retries after failure/cancellation use a new key. Report, answer aggregate, XP and task completion commit in one fenced transaction. A cancelled or expired worker cannot publish; a final task-write failure rolls back every preceding domain write.
- The shared JSON stage revalidates a checkpoint without initializing a provider client. Provider configuration is checked before reserving an external attempt; an empty DeepSeek key cannot fall back to unrelated `OPENAI_API_KEY` credentials. Model/validation attempts share the same three-attempt ceiling and queue-wide daily limits.
- Report UI now shows actual stages, supports explicit cancellation, restores an account/quiz-namespaced request after refresh, and cancels only transport on page hide. Task history links both the quiz and its task. Restoration validates the task kind and quiz identity before displaying a result.
- Real isolated MySQL tests cover duplicate admission, cross-user refusal, known-response recovery under a new lease, exactly-once XP, cancellation and transaction rollback. The browser checkpoint fixture is explicitly synthetic and performs zero model calls; it exercises actual API, worker, database and UI behavior. It is not a model-quality score.
- Actual new report task: one model call, 913 returned tokens, 1711 ms provider-call log time, 5671 ms observed UI completion including polling. Server accuracy was 67% and XP was 14 for the synthetic three-question exercise. Different-device replay and the compatibility endpoint reused the same result. See `evidence/m3-report-live.json`; no currency cost or human diagnosis rating is inferred.
- After live verification, the API was restarted with provider keys disabled. `report-live.spec.ts` reuse mode verified the saved real report without another call. Actual screenshots: `14-report-task.png` (synthetic checkpoint), `15-durable-report.png` and `16-report-desktop.png` (real generated report).
- Browser iterations found an incorrect test assumption (`undefined` instead of the API's `null` for no report), zero spacing between report actions, and a history link that could not resume a pending report without local storage. Contract/layout/navigation assertions reproduce these separately; none was fixed by suppressing errors or bypassing persistence.
- Latest backend suite: 247 deterministic tests; isolated database suite: 18 tests; frontend units: nine. Weapp runtime/device validation remains pending. Full task graph, Socratic mode, diagnosis, legacy quiz/search/image task migration and M4 algorithms remain unfinished.
- Final browser regression after the history-link fix: five default scenarios passed in 27.1 seconds; three paid scenarios were explicitly skipped by default. The separate real report and no-new-call recovery runs passed. Both artifacts and TypeScript passed; final H5 entry gzip is 118792 bytes and weapp main is 562527 bytes (`evidence/m3-report-build-size.json`). The inherited Webpack uncompressed-entry warning and outdated Browserslist-data notice remain visible, not suppressed.

| ID / behavior | Implementation | Tests | Evidence |
| --- | --- | --- | --- |
| REPORT-03 durable, owned report admission | `services/report_service.py`, `repositories/job_repository.py` | `test_report_tasks.py` in separate unit and integration suites | `evidence/m3-report-live.json` |
| REPORT-04 atomic report/XP/task publication | `repositories/quiz_repository.py` | cancellation, final-write rollback, replay integration tests | 18-case isolated MySQL suite |
| REPORT-05 pending refresh and cross-device history | Taro report/task pages, `services/reportSession.ts` | `report-tasks.spec.ts`, `reportSession.test.ts` | `evidence/m3-report-task-ui.json`, H5 `14-report-task.png` |

## M3 Outbound and Image Boundary Loop

- Reproduced missing image-key fallback to the embedding key, quota-store failure allowing paid calls,
  missing-pool quota writes silently succeeding, and total image failure returning no notice. These
  now fail closed or return an explicit text-practice fallback. Existing endpoint derivation and the
  separate keys remain intact; no actual credential values changed.
- Added public HTTPS URL validation, connector DNS checks (including mixed public/private results),
  manual redirect checks, identity encoding, MIME/streamed-size bounds and a total timeout that
  includes admission wait. A malformed redirect regression now returns a safe service error.
  Tests also exercise the real aiohttp connector with a controlled private DNS result and verify
  that the socket-connection stage is never called.
- Real network smoke: one verified-TLS public PNG read, 15770 bytes, 228 ms for the full smoke,
  three private addresses blocked before network, zero model calls and zero COS writes.
  `scripts/verify_outbound.py --confirm-one-public-read` reproduces this bounded check;
  `evidence/m3-outbound-live.json` records the measured response hash and limitations.
- Deterministic backend regression: 294 passed in 10.47 seconds; Pyflakes checks passed.
  The DashScope import emits an upstream Assistants deprecation warning, not a failed image call.
  This module changes no UI behavior except failure notices and does not claim new native/device
  coverage. Atomic image quotas, image-provider/COS integration, PNG decoding and legacy public
  search extraction still require implementation and separate verification.

| ID / behavior | Implementation | Tests | Evidence |
| --- | --- | --- | --- |
| NET-01 bounded public asset downloads | `services/outbound_service.py` | `test_outbound_safety.py` | `evidence/m3-outbound-live.json` |
| IMAGE-01 separate credentials and closed quota failure | `services/image_service.py`, `repositories/image_repository.py` | `test_image_safety.py` | 294-test deterministic regression; no paid image verification claimed |

## M3 Durable Private Practice Loop

- Private document text exercises now use the same owned queue as indexing, retrieval, answers and
  reports. The synchronous compatibility endpoint waits for that job; the worker checkpoints its
  retrieval context and validated JSON response. Public-topic and image-enabled requests retain
  their old path and remain explicitly pending migration, not silently disabled.
- Admission rejects forged identity/grading fields, blank input and an empty document ID. It captures
  server-read document revisions and rechecks them before retrieval and inside the final publication
  transaction. Cancellation, source deletion/reindexing, a stale lease or a failed final job write
  cannot publish a quiz. The generic task result contains only its quiz reference and title.
- The Taro library saves an account/document-namespaced idempotency key and immediately opens a task
  URL. That URL and task history restore actual stages after refresh; hiding the page stops polling
  transport, while explicit cancellation changes server state. Completed tasks open the saved
  exercise, and only submitted questions disclose answers and explanations.
- A new database regression exposed a real cross-device race: active-task coalescing did not preserve
  the second request key after completion. Additive migration 7 retains bounded key aliases in the
  admission transaction. Four task kinds now test replay and conflicting payloads after completion;
  a 64-alias limit bounds storage while existing keys remain replayable. Both local isolated schemas
  were migrated; cloud MySQL and production configurations were not changed.
- A held-job transaction test then reproduced a lock-order hazard in the alias-to-job foreign key.
  Migration 8 changes its lifecycle constraint to the owner, without changing data. Alias lookups
  still verify owner and kind; user deletion cascades. Future independent task pruning must remove
  aliases explicitly. A cancelled-query test also reproduced rollback masking the original
  cancellation; the shared transaction helper now preserves that signal and closes broken connections.
- Browser checkpoint verification covers cancellation with no quiz, duplicate admission, refresh,
  pending/completed history links, no answer leakage, server submission and restoration. The first
  run exposed a fixture bug: duplicate material reservation returned an existing document ID, but
  the fixture used its proposed new ID. The fixture now respects the real reservation result;
  no duplicate/authorization assertion was removed. See `evidence/m3-quiz-task-ui.json`.
- One actual model run generated five questions across all three supported types. Measured usage:
  one embedding request (usage unavailable), one quiz request / 1689 returned tokens / 3924 ms model
  stage; UI ready in 10956 ms including navigation, retrieval and polling. No image, report or web
  calls. See `evidence/m3-quiz-live.json` and `m3-quiz-provider-usage.json`. Question semantics are not
  human-rated, and per-question quote/coverage checking is still pending.
- With model keys disabled again, the saved real quiz resumed without a new call. A submitted answer
  survived refresh and identical replay, while the other answers remained hidden. Runtime screenshots
  `17-practice-task.png` and `18-recovered-practice.png` use the synthetic checkpoint;
  `19-durable-practice.png` and `20-practice-desktop.png` show the real generated exercise.
- Existing private-quiz unit tests were moved from their former process-local mocks to the actual
  queue admission/wait contracts. Rejection, no-web-search and no-local-background-task assertions
  remain; real transaction tests independently cover persistence and recovery.
- A stale local task reference was reproduced in the real browser: every subsequent library attempt
  reused a nonexistent task. HTTP errors now retain their status code; a definitive 404/409/422
  clears that local request reference, while network failure preserves it to avoid duplicate billing.
- Final checkpoint regression: 304 deterministic backend cases (11.07 s), 29 isolated database
  cases (6.58 s), 11 frontend units, TypeScript and Pyflakes checks passed. Final H5 run passed
  seven scenarios in 41.7 s, including saved real-quiz reuse; three other paid scenarios were
  explicitly skipped. All runtime provider keys were disabled during this final browser run.
- Final consecutive H5/weapp builds and base-path artifact checks passed. H5 entry gzip is 119252
  bytes; weapp main is 566869 bytes, with a 21565-byte learning subpackage. Native runtime remains
  unverified. Webpack's 369 KiB uncompressed-entry warning and outdated Browserslist notice remain.
  Rechecked target GitHub `main` still points to the initial revision; no remote write was made.

| ID / behavior | Implementation | Tests | Evidence |
| --- | --- | --- | --- |
| QUIZ-04 durable private text generation | `services/quiz_task_service.py`, `llm/quiz_chain.py` | `test_quiz_tasks.py` in separate unit/DB suites | `evidence/m3-quiz-live.json` |
| QUIZ-05 fenced atomic publication | `repositories/quiz_repository.py` | cancel/delete/reindex/rollback/recovery DB tests | Isolated MySQL regression |
| QUIZ-06 task links and protected answers | Taro quiz/library/tasks, `quizSession.ts` | `quiz-tasks.spec.ts`, `quiz-live.spec.ts`, frontend units | H5 screenshots 17-20 |
| JOB-05 cross-device request-key binding | `repositories/job_repository.py`, migrations 7-8 | four-kind replay, conflict, alias limit, lock-order and isolation DB tests | `m3-quiz-task-ui.json` |

## M3 Question Evidence Loop (2026-09-14)

- Added a failing regression first: generated private questions had no source-evidence contract.
  The validator now rejects missing/unknown/duplicate/paraphrased quotations, forged source locations
  and insufficient fragment coverage. Locations are server-owned; a quote match is not a semantic
  correctness score. Legacy saved questions retain their original data, without invented sources.
- Quotes remain hidden until the corresponding answer is committed. Submission/history revalidate
  owner, current source version and exact content. Deleted/reindexed evidence becomes unavailable;
  no stale quote is returned. The actual MySQL test covers disclosure followed by deletion.
- Browser verification traverses generation, refresh, authoritative submission, original-source
  navigation, return, replay and task history. A failed first run exposed the old local API still
  listening after a Windows separator mismatch in process selection; verified project-only PIDs
  were restarted and the full scenario rerun. No assertion was disabled.
- Paid smoke is gated to `evaluation/fixtures/learning-rate.md`. All stored chunks must exactly
  occur in that public synthetic material, and the browser blocks any other document/image request.
  This check was added after safety review rejected a potentially private payload. The reviewed
  retry passed: 1 embedding + 1 quiz request, 1979 returned text tokens, 4306 ms model stage and
  13008 ms UI-ready time. Currency and embedding usage are not available. No image/report calls.
- Local paid providers remain enabled as requested; deterministic tests still isolate credentials
  and network. Deployment is not yet complete. Native CLI remains blocked: service-port activation
  returned a refused local connection, and a subsequent status check still reported disabled service.
  The IDE and its open projects were not closed; no native screenshot or publication is claimed.
- Verification: 317 offline tests, 29 isolated MySQL tests, 11 frontend units, TypeScript and Ruff
  passed. H5 full regression: 7 passed / 3 explicitly skipped in 48.5 s, including saved paid-output
  reuse with no new calls. Consecutive dual builds passed: H5 entry gzip 119314 bytes; weapp main
  568279 bytes, learning subpackage 21565 bytes. Warnings remain recorded, not suppressed.
- Evidence: `evidence/m3-quiz-live.json`, `evidence/m3-quiz-resume.json`,
  `evidence/m3-quiz-task-ui.json`, `evidence/m3-citations-build-size.json`;
  screenshots `19-durable-practice.png`, `20-practice-desktop.png`, `21-practice-source.png`,
  `22-cited-analysis.png` under `screenshots/h5/` are real Chromium captures.

| ID / behavior | Implementation | Tests | Evidence |
| --- | --- | --- | --- |
| QUIZ-07 exact question citations | `llm/quiz_chain.py`, `models/quiz.py` | `test_quiz_citations.py`, cached-response DB test | Bounded real quiz smoke |
| QUIZ-08 disclosure and current-source check | `quiz_evidence_service.py`, grading/history services | delete/reindex/owner unit and DB tests | Quiz browser scenarios and screenshots 19-22 |

## M4 Review State Loop (2026-09-15)

- First authoritative attempts now atomically update owner-scoped BKT observations, FSRS cards and
  learning events. A versioned review is server-graded and idempotent; no review XP is added. The
  frontend restores a lost response after reload and renders real due counts and activity trends.
- Wrong-answer filtering, favorites and user-confirmed error categories persist; named notebooks
  are a separate pending request. Default BKT and FSRS parameters are disclosed, not described as
  personal training. See `learning-algorithms.md` for transaction, timezone and uncertainty details.
- Verification: 332 offline cases; 33 isolated database cases passed in two consecutive runs; 11
  frontend units and TypeScript passed. The full real-browser regression passed 8 scenarios in
  58.1 s, including saved paid-quiz reuse; 3 opt-in paid scenarios skipped, no new paid calls.
- Repeated database runs exposed an accumulating synthetic provider ledger. The isolated fixture
  now locks, snapshots and restores its ledger per case. Limits and production data are unchanged.
- Consecutive builds: H5 entry gzip 119827 bytes; weapp main 572220 bytes and learning subpackage
  33753 bytes. Entry-size/Browserslist and MySQL 8 `VALUES()` deprecation warnings remain visible.
- Runtime evidence: `evidence/m4-review-ui.json`, `evidence/m4-review-build-size.json`, and H5
  screenshots 07, 23-25. Native IDE verification remains pending; no deployment changes were made.

| ID / behavior | Implementation | Tests | Evidence |
| --- | --- | --- | --- |
| LEARN-01 authoritative observations | `learning_state_service.py`, migration 9 | `test_learning_state.py` atomic rollback/replay | Real API + MySQL |
| LEARN-02 explainable BKT / FSRS | `learning/` | `test_learning_algorithms.py` | Versioned events and review UI |
| REVIEW-01 versioned due review | `learning/review`, `/learning/cards` | lost-response browser test, ownership / time DB tests | Screenshots 07, 23 |
| REVIEW-02 wrong / favorites / trend | owner-filtered learning routes | `review.spec.ts`, timezone / DST tests | Screenshots 24-25 |

## Scope Addendum (2026-09-15)

The following owner requests are part of the remaining acceptance scope, not completed claims:

| ID | Requested behavior | Acceptance requirement | Status |
| --- | --- | --- | --- |
| QUIZ-09 | User-selected total and per-type counts | Single, multiple, fill-in, judgment and written response; exact blueprint validation; bounded task batches and authoritative scoring | Pending |
| REPORT-04 | Mermaid learning and relationship diagrams | Stored graph data after review; sanitized H5 renderer and tested native equivalent; invalid graphs fail visibly | Pending |
| REVIEW-03 | Named error notebooks | Create notebook, explicitly add/remove an owned wrong question, select destination, idempotency and cross-user denial | Implemented; isolated DB and H5 verified; native runtime pending |
| UI-04 | Visible companion and recovery | Focus pages must not silently remove it; safe collapsed state, restore/hide control, mobile/desktop/native checks | H5 fixed and verified; native build passed, IDE runtime pending |
| UI-05 | Simpler hand-painted anime visual design | Original nature/study artwork, restrained surfaces and typography, no pervasive dot field or generic AI marketing composition; five themes and real screenshots | H5 simplified and verified across five themes; native runtime pending |

GitHub code pushes are explicitly authorized; credentials must never be uploaded. Local paid model
providers remain enabled with budgets. Deployment-side paid providers still require actual deployment
and verification. This addendum extends the original M0-M7 scope, without removing pending security,
algorithm-experiment, native-testing, documentation or coexistence requirements.

## Continuing Decisions

### Five-Type Practice and Durable Written Assessment (2026-09-15)

- Total 1-20 and individual single/multiple/judge/fill/written counts are validated on both ends.
  Sets larger than five use quota-preserving batches with independent saved provider checkpoints;
  repeated stems and incorrect distributions are rejected before publication. Text input drafts
  survive refresh. Reference answers, accepted fill variants and written rubrics stay server-side
  until the corresponding submission is published.
- Fill grading uses ordered normalized accepted variants. Written grading is a durable, bounded
  DeepSeek task with strict criterion coverage and exact student-quote checks. Correctness is derived
  by the server from all criteria, not from a client or model-supplied score. This is labeled model
  judgment, not guaranteed semantic correctness or a human accuracy measurement.
- Same-answer concurrent request keys coalesce. Changed answers conflict; owner, card version and
  lease fencing are checked. The grade, learning observation, review event and task publication share
  one transaction. Cancellation and a failed commit do not publish partial learning updates.
- Verification: 352 offline tests, 39 isolated MySQL tests, 13 frontend units, TypeScript and backend
  Ruff F checks passed. Full H5 run: 13 passed in 1.1 minutes, 3 extra paid scenarios explicitly
  skipped. A saved real model response was rendered without another model call. Both sequential
  builds and base-path checks passed; H5 entry gzip 120447 bytes, weapp main 977192 bytes.
- Bounded live integration on the public learning-rate fixture: five requested types returned,
  four objective submissions and one real rubric assessment completed. Three external calls,
  2531 provider-reported tokens; currency cost is not known. Reference-answer submission proves
  integration, not student learning quality. Local paid providers remain enabled.
- Evidence: `evidence/text-quiz-live.json`, `evidence/text-practice-ui.json`,
  `evidence/text-practice-build-size.json`, real H5 screenshots 32-36. Contracts, commands and limits:
  `practice-and-assessment.md`. Native CLI still reports disabled service port; no native runtime
  success, production deployment or public availability is claimed.

| ID | Implementation | Tests | Evidence |
| --- | --- | --- | --- |
| QUIZ-04 | `quiz_blueprint.py`, `quiz_batches.py`, `QuestionCountsEditor.tsx` | `test_quiz_blueprint.py`, `test_text_grading.py`, frontend counts units | H5 screenshot 32, live five-type result |
| QUIZ-05 | `written_grading.py`, `written_grade_service.py`, `TextAnswer.tsx` | `integration/test_written_grading.py`, `e2e/text-practice.spec.ts` | H5 screenshots 33-36, isolated persistence and real paid response |

### Page Artwork Loop (2026-09-15)

- Added two original painted scenes after the owner's background-art request: a 1280x853 courtyard
  behind the login screen and a 1200x400 notebook shelf inside an unframed library band. Mobile
  login uses a deliberate central crop; the shelf always preserves the entire source composition.
  The form is opaque in both light and night themes. No customer/reference-project assets were used.
- Added a failing browser acceptance test before integration, then verified decoded image sizes,
  JPEG media type, login form backgrounds, visible upload control, nonoverlap and horizontal bounds
  at widths 320, 390 and 1440. Three relevant browser scenarios passed in 12.6 s, including a real
  file upload and persisted parse error. TypeScript and 11 frontend units passed.
- Sequential H5/weapp builds and base-path checks passed: H5 entry gzip 120253 bytes; native main
  package 964840 bytes. Native IDE execution is still unverified. Images added 261344 source bytes;
  these are not remotely loaded and contain no credentials. Preview now serves JPEG/WebP MIME types.
- Evidence: `evidence/artwork-ui.json`, `evidence/artwork-build-size.json`, real screenshots 29-31
  under `screenshots/h5/`. Prompts, export dimensions and distribution caveats are documented in
  `assets-attribution.md`. No paid backend calls or production changes were needed for this loop.

### Named Error Notebooks (2026-09-15)

- Migration 10 adds owned notebooks and memberships without changing original attempts or review
  schedules. Creation and repeated insertion are idempotent; rename/delete use versions. Composite
  foreign keys prevent cross-owner memberships. The API rejects correct-only cards and forged
  request identity. No question is automatically added to a named notebook.
- Learners can create, select, rename and delete notebooks, explicitly collect a wrong question
  from answer analysis or a report, and remove only its membership. Deleting a notebook retains
  the original wrong-answer record, BKT observations and FSRS schedule.
- Added failing tests before implementation. Verification: 332 offline tests, 35 isolated MySQL
  tests, TypeScript and touched-backend Ruff checks passed. The full H5 suite passed 10 scenarios;
  3 opt-in paid scenarios skipped. Saved paid quiz output was reused without a new provider call.
- Screenshot inspection found low-contrast Taro button text and a companion overlapping the
  changed toolbar. Added regressions before fixing explicit ink color and debounced layout/scroll
  avoidance; observers and timers are disposed on unmount. Native code builds, but IDE execution
  is still pending. H5 gzip entry: 120047 bytes; weapp main: 701647 bytes.
- Evidence: `evidence/notebooks-ui.json`, `evidence/notebooks-build-size.json`, H5 screenshots
  `27-notebook-destination.png` and `28-error-notebook.png`.
- Limits: at most 30 notebooks per account, 80-character names and 50 cards per current list query.
  Historical attempts predating learning-card migration have not been backfilled. Migration 10
  has only run against isolated local/test databases; production is unchanged.

| ID | Implementation | Tests | Evidence |
| --- | --- | --- | --- |
| REVIEW-03 | `notebook_service.py`, learning routes, `NotebookDialog.tsx`, review page | `integration/test_notebooks.py`, `e2e/notebooks.spec.ts` | Actual API/DB and H5 screenshots 27-28 |

### Companion Visibility Regression (2026-09-15)

- Reproduced focus-page removal in Chromium before changing the shell. A persistent topbar partner
  control now stays available, including when floating placement cannot find room. Focus pages
  expand into reserved document-flow space. Hide, fold and restore are separate states.
- Screenshot review found a second defect: animated `transform` replaced the Taro image's centering
  transform, clipping the expanded character. A failing full-image-bounds test was added before the
  correction. The native drag release also reads current, not initial, viewport dimensions.
- Two browser scenarios passed in 9.9 s: focus display, full portrait, no answer overlap, persisted
  fold/hide and restore, crowded 320x330 fallback, desktop recovery, drag, all five themes and motion.
  Existing frontend units/typecheck remain passing. Both builds passed; H5 entry gzip 119949 bytes,
  weapp main 574180 bytes. Native IDE runtime remains unverified, not described as fixed by a build.
- Evidence: `evidence/companion-visibility.json`, `evidence/companion-build-size.json`, and the actual
  H5 screenshot `screenshots/h5/26-companion-focus.png`. No provider calls or production changes.

### Hand-Painted Interface Loop (2026-09-15)

- Removed pervasive dot/grid backgrounds, reduced the oversized heading reservation and replaced
  promotional home copy with literal learning labels. Five themes retain stable navigation and
  individual accent, border and typography choices on restrained surfaces.
- Added one original 1280x427 study-library illustration (120801 bytes). It is decorative artwork,
  explicitly attributed in `assets-attribution.md`, not a system screenshot or a reference-project
  asset. The runtime screenshots show the actual browser interface and real isolated test data.
- Three browser scenarios passed in 15.3 s: five themes, mobile/small/desktop layouts, artwork load,
  companion rendering and recovery, and the complete server-backed review flow. H5 and weapp builds
  passed; native IDE execution still requires verification. Source bounds and UI overlap assertions
  remain enabled. Evidence: refreshed screenshots 01, 07, 09-10, 23-26 and `theme-*.png`.

- Preserve Taro 4.1.11, MySQL and Chroma; enhance existing modules.
- Deterministic tests must disable dotenv and network before importing the application.
- External credentials are consumed from private files, never logged. Existing SSH host keys must verify before login.
- New learning tables require isolated migration verification and backup before production use.
- The current embedded Chroma runtime uses one API process with one controlled worker loop. This shares the vector-store process and avoids a second Chroma service on the constrained host. A separate multi-process vector deployment is not claimed or enabled.
- MySQL owns task delivery, leases, cancellation, checkpoints and budgets. No Redis or message broker is introduced for this queue. An uncertain provider outcome fails explicitly instead of promising exactly-once billing.
- No claim of OCR, model training, real-device testing, public availability or performance improvement without recorded execution.
