# Optional Practice Illustrations

Illustrations are explicitly enabled per practice request, off by default. Up to the first two
questions receive a separate owned `image` job after the text quiz is committed. Text questions
remain usable if image admission reaches a quota, image generation fails, or the learner cancels
the image task. These are optional AI illustrations, not verified answer evidence.

## Boundaries

`quiz_task_service` validates static configuration. `quiz_repository.publish_generated_quiz`
commits text, provenance and child admission together; a child task quota error rolls back only
the child savepoint. Migration 13 adds owned asset references. Image work uses the same bounded
MySQL worker, leases, checkpoints and call ledger as other tasks. No process-local quiz task is
created by either synchronous or asynchronous API routes.

`quiz_image_repository.reserve` locks the user before reserving the daily image count. Attempts
are counted before calling the provider, including failed or uncertain calls. Replaying a saved
reservation does not increment the quota. The default is 20 reservations per user per UTC day,
configurable from 1 to 100. Each job allows at most two images and one provider attempt per image.
Known authorization/configuration/quota failure prevents calls for later images. A saved provider
URL is reused for storage recovery; an uncertain provider outcome is not silently regenerated.

Generation uses the separate `DASHSCOPE_IMAGE_API_KEY`, never the embedding key. An empty image
base URL is derived from the configured embedding endpoint. Requests use the native HTTPS
[Qwen-Image API](https://www.alibabacloud.com/help/en/model-studio/qwen-image-api), `n=1`, explicit
size, negative prompt, disabled prompt extension and no HTTP retries or redirects. The HTTP
timeout is 35 seconds, with a 40-second outer deadline and the shared job deadline. Response
JSON is limited to 64 KiB. This is provider integration, not model fine-tuning or OCR.

Downloaded PNG/JPEG bytes pass the existing public-network/DNS-pinned downloader. The 8 MiB
input cap, 4,194,304-pixel cap and Pillow dimension checks precede decoding. Images become JPEG
thumbnails at most 640x640 and 350 KB, without embedded metadata. The display uses aspect-fit,
not an arbitrary crop.

## Private Storage And Answer Release

Only a task's reserved `COS_UPLOAD_PREFIX/ai-learn-private-v1/asset_*.jpg` key may be written or
deleted. Before a model call, the worker writes a non-sensitive marker to that tracked key with
private ACL and requires an anonymous request to return 403. It then overwrites only that key
with the illustration, again checking anonymity denial. No bucket policy or existing object is
modified. COS SDK retries are zero, connection pools are two and request timeout is ten seconds.

The database stores asset IDs, not permanent public URLs. Authenticated image retrieval checks
quiz ownership, source revision, job completion and a server-persisted answer for that question.
Before submission, a ready asset reports `locked` with no URL. After scoring, the endpoint issues
a 120-second signed URL. A copied signed URL is a temporary bearer capability; deletion or logout
cannot revoke it instantaneously. URLs must never be placed in public logs or documentation.
Unanswered question serialization also withholds knowledge-point labels and legacy image URLs,
because either can reveal an answer even when the `answer` field is hidden.

Publication locks source revisions before the job row. Cancellation, a lost lease or deleted /
rebuilt source prevents publication. Cleanup only considers tracked failed/cancelled/stale assets
older than ten minutes, at most four per cycle. Storage deletion has no SDK retry; a failed cleanup
is attempted at most five cycles with ten-minute spacing. After that it needs operator attention.
Do not change the COS prefix without a migration/recovery plan for already tracked keys.

## Executed Verification

- Deterministic tests cover dedicated credentials, native request shape, one-image requests,
  status failures, privacy probe refusal, pixel limits and saved-response recovery.
- Real isolated MySQL tests cover concurrent quota reservations, cancellation, ownership,
  rollback, source revision fencing, answer release, child-admission quotas and cleanup bounds.
- Browser tests use actual API/worker/database state. Synthetic image checkpoints contain a
  prewritten failure outcome before becoming visible to the worker, so they cannot call models.
  They exercise cancellation, refresh, continued answer submission and polling disposal.
- The first paid integration used one text call (841 tokens) and one unmetered image call, in
  9650 ms. Private access checks passed, but screenshot inspection found instruction-like text
  inside the image and a pre-answer hint risk. This was not accepted as a content-quality pass.
- After adding visual-only prompting and server-gated answer release, the second run used one
  text call (869 tokens) and one unmetered image call, in 10811 ms. The resulting 512x512 JPEG is
  29573 bytes. Anonymous reads returned 403; another user's API read returned 404. Currency cost
  is unknown, not zero. These two paid runs consumed four provider calls total, not a benchmark.

The second generated image was visually inspected as a stylized leaf illustration. No automatic
scientific-accuracy or text-free image guarantee is claimed. Diagram correctness requires human
review; the product marks it as non-evidence. An earlier startup-only smoke failed before any
request could reach the API and made no provider call.

Evidence: [live request metrics](evidence/quiz-image-live.json),
[browser checks](evidence/quiz-image-ui.json), [build sizes](evidence/quiz-images-build-size.json),
[real H5 illustration](screenshots/h5/42-live-private-illustration.png) and
[synthetic failure state](screenshots/h5/43-image-failure-text-preserved.png).

```powershell
# From the repository root; the isolated local API must be running first.
backend/venv/Scripts/python.exe scripts/test_offline.py -q
backend/venv/Scripts/python.exe scripts/test_database.py
# Explicit paid smoke, using the private local fixture established by text-practice verification:
backend/venv/Scripts/python.exe scripts/smoke_quiz_image.py --paid
cd frontend
$env:AI_LEARN_IMAGE_REUSE='1'
npx playwright test e2e/illustrations.spec.ts
```

The ready-image browser case reuses the saved private fixture and makes no new model call. Native
builds are not native execution evidence. WeChat download domains, device behavior and production
deployment still need separate verification. There is currently no automatic regenerate button:
retrying image *reading* refreshes a signed URL, never purchases another generation silently.
