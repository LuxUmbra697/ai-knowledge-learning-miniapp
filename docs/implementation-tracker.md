# Implementation and Verification Ledger

Started: 2026-09-11 (Asia/Shanghai). Initial revision: `148970c`.
This ledger records observed results; planned capabilities are not delivery claims.

## Stages

| Stage | Acceptance | State | Evidence |
| --- | --- | --- | --- |
| M0 | Isolated baseline; authenticated ownership; authoritative grading; safe config | Core checks passed; release hardening continues | `evidence/m0-local.json`; 159 deterministic tests |
| M1 | Taro H5/weapp, separate outputs, independent login, five themes | H5 core flow passed; native runtime gate pending | `frontend/e2e`; `screenshots/h5`; DevTools service port unavailable |
| M2 | Bounded parsing, scoped hybrid retrieval, citations, 100-case evaluation | Retrieval/citation checkpoint verified; remaining gates below | 104 synthetic cases; real index and answer evidence; dual builds |
| M3 | Bounded learning agent, durable worker, cancellation/recovery | Starting with persistent task lifecycle | Existing task table reviewed; in-process execution remains a release blocker |
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

## Decision Record

- Preserve Taro 4.1.11, MySQL and Chroma; enhance existing modules.
- Deterministic tests must disable dotenv and network before importing the application.
- External credentials are consumed from private files, never logged. Existing SSH host keys must verify before login.
- New learning tables require isolated migration verification and backup before production use.
- No claim of OCR, model training, real-device testing, public availability or performance improvement without recorded execution.
