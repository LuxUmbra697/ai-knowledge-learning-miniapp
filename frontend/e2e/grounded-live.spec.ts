import { test, expect } from '@playwright/test'
import { readFile, writeFile } from 'node:fs/promises'

test('live grounded answer resolves a real source without exposing raw HTML', async ({ page }) => {
  test.skip(process.env.AI_LEARN_LIVE_E2E !== '1', 'Explicit opt-in: one retrieval plus at most three bounded chat calls')
  test.setTimeout(90000)
  const fixture = JSON.parse(await readFile('../.local/m2-browser.json', 'utf8'))
  const errors: string[] = []
  const reuse = process.env.AI_LEARN_LIVE_REUSE_LAST === '1'
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('pages/login/index')
  await page.evaluate(identity => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: identity.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: identity.user }))
  }, fixture.account)
  await page.goto('pages/knowledge/index')
  await expect(page.getByText('学习率补充讲义.md', { exact: true })).toBeVisible()
  await page.screenshot({ path: '../docs/screenshots/h5/02-knowledge-library.png', fullPage: true })
  let task: { task_id: string }
  if (reuse) {
    const history = (await (await page.request.get('api/v1/learning/tasks', { headers: { Authorization: `Bearer ${fixture.account.token}` } })).json()).data.items
    task = history.find(item => item.kind === 'answer' && item.status === 'completed')
    expect(task).toBeTruthy()
    await page.evaluate(({ userId, taskId, docId }) => localStorage.setItem(`ai-learn:v1:answer:${userId}`, JSON.stringify({ data: { taskId, docIds: [docId], query: '学习率过大会怎样？过小又会怎样？' } })), { userId: fixture.account.user.id, taskId: task.task_id, docId: fixture.doc_id })
    await page.getByText('向材料提问', { exact: true }).click()
  } else {
    await page.getByText('向材料提问', { exact: true }).click()
    await expect(page.locator('.ask-actions')).toContainText('已选择 1 篇材料')
    await page.locator('textarea').fill('学习率过大会怎样？过小又会怎样？')
    const responsePromise = page.waitForResponse(response => response.url().endsWith('/knowledge/ask/async'))
    await page.getByText('提问', { exact: true }).click()
    const response = await responsePromise
    expect(response.status()).toBe(200)
    task = (await response.json()).data
    await page.waitForFunction(({ userId, taskId }) => JSON.parse(localStorage.getItem(`ai-learn:v1:answer:${userId}`) || '{}').data?.taskId === taskId, { userId: fixture.account.user.id, taskId: task.task_id })
    const pending = await page.evaluate(userId => JSON.parse(localStorage.getItem(`ai-learn:v1:answer:${userId}`) || '{}').data, fixture.account.user.id)
    const replay = await page.request.post('api/v1/knowledge/ask/async', { headers: { Authorization: `Bearer ${fixture.account.token}`, 'Idempotency-Key': pending.key }, data: { query: pending.query, doc_ids: pending.docIds } })
    expect((await replay.json()).data.task_id).toBe(task.task_id)
  }
  await page.reload()
  await expect(page.getByText('来自学习材料的回答', { exact: true })).toBeVisible({ timeout: 65000 })
  const finished = await page.request.get(`api/v1/learning/tasks/${task.task_id}`, { headers: { Authorization: `Bearer ${fixture.account.token}` } })
  const stored = (await finished.json()).data
  expect(stored.status).toBe('completed')
  expect(stored.trace.model_calls).toBeLessThanOrEqual(4)
  const answer = stored.result
  expect(answer.status).toBe('answered')
  expect(answer.trace.model_calls).toBeLessThanOrEqual(3)
  expect(answer.evidence.length).toBeGreaterThan(0)
  await expect(page.getByText('来自学习材料的回答', { exact: true })).toBeVisible()
  await expect(page.locator('.claim-text').first()).toBeVisible()
  await expect.poll(async () => (await page.locator('.grounded-response').boundingBox())?.y || 0).toBeLessThan(200)
  expect(await page.locator('body').evaluate(node => node.scrollWidth <= window.innerWidth)).toBeTruthy()
  await page.screenshot({ path: '../docs/screenshots/h5/04-grounded-chat.png', fullPage: true })
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.screenshot({ path: '../docs/screenshots/h5/11-grounded-desktop.png', fullPage: true })
  await page.locator('.citation-link').first().click()
  await expect(page.locator('.original-content')).toContainText('学习率决定一次参数更新的步长')
  await expect(page.locator('.page-title').filter({ hasText: /^原文证据$/ })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: '../docs/screenshots/h5/12-source-evidence.png', fullPage: true })
  await page.reload()
  await expect(page.locator('.original-content')).toContainText('设置过大会导致震荡')
  expect(errors).toEqual([])
  await writeFile(`../docs/evidence/${reuse ? 'm3-answer-resume' : 'm3-live-answer'}.json`, JSON.stringify({ recorded_at: new Date().toISOString(),
    environment: 'Playwright Chromium + loopback API + isolated MySQL/Chroma + actual provider',
    source: 'synthetic teaching fixture', status: answer.status, claim_count: answer.claims.length,
    citation_count: answer.claims.reduce((sum, claim) => sum + claim.citations.length, 0), trace: answer.trace, task_trace: stored.trace,
    run_mode: reuse ? 'reuse previously completed real answer; zero new model calls' : 'new bounded real task',
    checks: ['selected_document', 'actual_model_answer', 'owned_exact_citation', 'source_navigation', 'direct_refresh', '390_and_1440_width', 'no_page_errors', ...(reuse ? [] : ['idempotency_replay_same_task']), 'answer_resumes_after_reload', 'persisted_call_budget'],
    limitations: ['No human semantic correctness rating', 'No native WeChat execution'] }, null, 2) + '\n')
})
