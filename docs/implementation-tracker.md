# Implementation and Verification Ledger

Started: 2026-09-11 (Asia/Shanghai). Initial revision: `148970c`.
This ledger records observed results; planned capabilities are not delivery claims.

## Stages

| Stage | Acceptance | State | Evidence |
| --- | --- | --- | --- |
| M0 | Isolated baseline; authenticated ownership; authoritative grading; safe config | Core checks passed; release hardening continues | `evidence/m0-local.json`; 159 deterministic tests |
| M1 | Taro H5/weapp, separate outputs, independent login, five themes | H5 core flow passed; native runtime gate pending | `frontend/e2e`; `screenshots/h5`; DevTools service port unavailable |
| M2 | Bounded parsing, scoped hybrid retrieval, citations, 100-case evaluation | Retrieval/citation checkpoint verified; remaining gates below | 104 synthetic cases; real index and answer evidence; dual builds |
| M3 | Bounded learning agent, durable worker, cancellation/recovery | Index, retrieval and answer queue checkpoint verified; practice/report migration and tutoring graph pending | MySQL restart/cancellation tests, real index/answer tasks and H5 task history |
| M4 | Mastery, FSRS, prerequisites, reproducible offline experiment | Pending | No implementation yet |
| M5 | Browser and DevTools workflows, screenshots, regression | In progress alongside each module | Actual H5 screenshots exist; no weapp screenshots claimed |
| M6 | New deployment plus all existing sites healthy | Pending | No gateway mutations |
| M7 | Bilingual README, documentation, private handoff, GitHub and CI | Pending | Remote history verified |

## Requirement Traceability

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

## Architecture Decisions

- Preserve Taro 4.1.11, MySQL and Chroma; enhance existing modules.
- Deterministic tests must disable dotenv and network before importing the application.
- External credentials are consumed from private files, never logged. Existing SSH host keys must verify before login.
- New learning tables require isolated migration verification and backup before production use.
- The current embedded Chroma runtime uses one API process with one controlled worker loop. This shares the vector-store process and avoids a second Chroma service on the constrained host. A separate multi-process vector deployment is not claimed or enabled.
- MySQL owns task delivery, leases, cancellation, checkpoints and budgets. No Redis or message broker is introduced for this queue. An uncertain provider outcome fails explicitly instead of promising exactly-once billing.
- No claim of OCR, model training, real-device testing, public availability or performance improvement without recorded execution.
