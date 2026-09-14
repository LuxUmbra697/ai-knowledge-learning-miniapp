import { test, expect } from '@playwright/test'
import { readFile, writeFile } from 'node:fs/promises'

test('real document practice, authoritative answers and persisted model report', async ({ page, request }) => {
  test.skip(process.env.AI_LEARN_LIVE_PRACTICE !== '1', 'Explicit opt-in: one embedding and at most three calls per quiz/report stage')
  test.setTimeout(180000)
  const fixture = JSON.parse(await readFile('../.local/m2-browser.json', 'utf8'))
  const headers = { Authorization: `Bearer ${fixture.account.token}` }
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const get = async (url: string) => {
    const response = await request.get(`api/v1/${url}`, { headers })
    expect(response.status()).toBe(200)
    return (await response.json()).data
  }
  const baseline = await get('user/profile')
  await page.goto('pages/login/index')
  await page.evaluate(identity => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: identity.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: identity.user }))
  }, fixture.account)
  const started = Date.now()
  let quizId: string
  const reuse = process.env.AI_LEARN_PRACTICE_REUSE === '1'
  if (reuse) {
    quizId = JSON.parse(await readFile('../.local/practice-browser.json', 'utf8')).quizId
    await page.goto(`pages/quiz/index?quizId=${quizId}`)
  } else {
    await page.goto('pages/knowledge/index')
    await expect(page.getByText('学习率补充讲义.md', { exact: true })).toBeVisible()
    await page.getByText('知识练习', { exact: true }).click()
    await page.waitForURL(/pages\/quiz\/index\?taskId=/, { timeout: 100000 })
    const taskId = new URL(page.url()).searchParams.get('taskId')!
    await expect(page.locator('.question-stem')).toBeVisible({ timeout: 75000 })
    quizId = (await get(`learning/tasks/${taskId}`)).result.quiz_id
    await writeFile('../.local/practice-browser.json', JSON.stringify({ quizId }) + '\n')
  }
  const quizReadyMs = Date.now() - started
  let detail = await get(`user/quizzes/${quizId}`)
  expect(detail.questions).toHaveLength(5)
  expect(new Set(detail.questions.map(q => q.type))).toEqual(new Set(['single', 'multiple', 'judge']))
  const alreadySubmitted = new Set((detail.answer_records || []).map(record => record.question_id))
  for (const question of detail.questions) {
    if (alreadySubmitted.has(question.id)) continue
    expect(question).not.toHaveProperty('answer')
    expect(question).not.toHaveProperty('explanation')
    await expect(page.getByText(question.stem, { exact: true })).toBeVisible()
    await page.locator('.answer-option').nth(0).click()
    if (question.type === 'multiple') await page.locator('.answer-option').nth(1).click()
    const submitted = page.waitForResponse(response => response.url().endsWith(`/quiz/${quizId}/answer`))
    await page.getByText('确认答案', { exact: true }).click()
    expect((await submitted).status()).toBe(200)
    // A fresh page must restore the next unanswered question from server records.
    await page.reload()
  }
  detail = await get(`user/quizzes/${quizId}`)
  expect(detail.answer_records).toHaveLength(5)
  const correct = detail.answer_records.filter(record => record.is_correct).length
  for (const record of detail.answer_records) {
    const question = detail.questions.find(item => item.id === record.question_id)
    expect(record.is_correct).toBe([...record.selected_answers].sort().join(',') === [...question.answer].sort().join(','))
  }
  await page.goto(`pages/report/index?quizId=${quizId}`)
  await expect(page.getByText(`${Math.round(correct / 5 * 100)}%`, { exact: true })).toBeVisible()
  const reportStarted = Date.now()
  if (!detail.report) {
    const generated = page.waitForResponse(response => response.url().endsWith('/report/generate/async'), { timeout: 15000 })
    await page.getByText('生成学习报告', { exact: true }).click()
    expect((await generated).status()).toBe(200)
    await page.reload()
  }
  await expect(page.getByText('本次总结', { exact: true })).toBeVisible({ timeout: 70000 })
  const reportReadyMs = Date.now() - reportStarted
  await page.screenshot({ path: '../docs/screenshots/h5/08-learning-report.png', fullPage: true })
  await page.reload()
  await expect(page.getByText('本次总结', { exact: true })).toBeVisible()
  const persisted = await get(`user/quizzes/${quizId}`)
  expect(persisted.report.accuracy).toBe(Math.round(correct / 5 * 100))
  const repeated = await request.post('api/v1/report/generate', { headers, data: { quiz_id: quizId } })
  expect(repeated.status()).toBe(200)
  expect((await repeated.json()).data).toEqual(persisted.report)
  const after = await get('user/profile')
  expect(after.total_xp - baseline.total_xp).toBe(detail.report ? 0 : 10 + correct * 2)
  const stranger = (await (await request.post('api/v1/user/account/register', { data: { username: `e2e_report_${Date.now()}`, password: 'Local-E2E-Only-1976' } })).json()).data
  const forbidden = await request.post('api/v1/report/generate', { headers: { Authorization: `Bearer ${stranger.token}` }, data: { quiz_id: quizId } })
  expect(forbidden.status()).toBe(404)
  expect(errors).toEqual([])
  expect(await page.locator('body').evaluate(node => node.scrollWidth <= window.innerWidth)).toBeTruthy()
  await writeFile(`../docs/evidence/m3-practice-${reuse ? 'resume' : 'live'}.json`, JSON.stringify({
    recorded_at: new Date().toISOString(), environment: `Chromium + loopback API + isolated MySQL/Chroma + ${reuse ? 'saved real-provider fixture' : 'real provider'}`,
    source: 'Synthetic learning-rate teaching document, not user study data', quiz_ready_ms: quizReadyMs,
    report_ready_ms: reportReadyMs, question_count: 5, types: ['single', 'multiple', 'judge'],
    correct_count: correct, report_accuracy: persisted.report.accuracy, xp_delta: after.total_xp - baseline.total_xp,
    checks: [...(reuse ? [] : ['knowledge_library_entry', 'answer_fields_hidden_before_submission', 'reload_restores_answers']),
      'server_grading_matches_stored_answers', 'report_matches_server_score', 'report_persists_after_refresh', 'report_replay_returns_same_result',
      'xp_awarded_once', 'cross_user_report_404', 'no_browser_errors', '390px_no_horizontal_overflow'],
    limitations: ['Model-generated question semantics are not human-rated', 'Legacy image/public-topic quiz jobs are not yet restart-safe',
      'No native WeChat execution', 'Provider usage must be read from redacted stage logs, not inferred from HTTP count'],
  }, null, 2) + '\n')
})
