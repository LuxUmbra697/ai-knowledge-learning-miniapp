import { test, expect } from '@playwright/test'
import { readFile, writeFile } from 'node:fs/promises'

test('bounded real private practice task restores and publishes server-graded questions', async ({ page, request }) => {
  test.skip(process.env.AI_LEARN_LIVE_QUIZ !== '1', 'Explicit opt-in: one embedding and at most three quiz calls, no image or report generation')
  test.setTimeout(100000)
  const source = JSON.parse(await readFile('../.local/m2-browser.json', 'utf8'))
  const identity = source.account
  const headers = { Authorization: `Bearer ${identity.token}` }
  const get = async (url: string) => {
    const response = await request.get(`api/v1/${url}`, { headers })
    expect(response.status()).toBe(200)
    return (await response.json()).data
  }
  const before = await get('user/profile')
  const publicFixture = await readFile('../evaluation/fixtures/learning-rate.md', 'utf8')
  const material = await get(`knowledge/documents/${source.doc_id}/chunks`)
  expect(material.total).toBe(material.items.length)
  expect(material.items.length).toBeGreaterThan(0)
  for (const chunk of material.items) {
    expect(chunk.doc_id).toBe(source.doc_id)
    expect(publicFixture.includes(chunk.content)).toBe(true)
  }
  await page.route('**/quiz/generate/async', async route => {
    const payload = route.request().postDataJSON()
    if (payload.doc_id !== source.doc_id || payload.generate_images) {
      await route.abort()
      throw new Error('Paid smoke can use only the verified public synthetic fixture, with images disabled')
    }
    await route.continue()
  })
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const settle = async () => {
    await expect.poll(() => page.locator('body').evaluate(node => node.scrollWidth <= window.innerWidth)).toBe(true)
  }
  const scrollTop = async () => {
    await page.evaluate(() => {
      for (const node of document.querySelectorAll('*')) if (node.scrollTop) node.scrollTop = 0
      window.scrollTo(0, 0)
    })
    await settle()
  }
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, identity)
  const reuse = process.env.AI_LEARN_QUIZ_REUSE === '1'
  let taskId: string
  const started = Date.now()
  if (reuse) {
    ({ taskId } = JSON.parse(await readFile('../.local/quiz-browser.json', 'utf8')))
    await page.goto(`pages/quiz/index?taskId=${taskId}`)
  } else {
    await page.goto('pages/knowledge/index')
    const document = page.locator('.document-row').filter({ has: page.getByText('学习率补充讲义.md', { exact: true }) })
    await expect(document).toBeVisible()
    const pending = page.waitForResponse(response => response.url().endsWith('/quiz/generate/async'))
    await document.getByText('知识练习', { exact: true }).click()
    const response = await pending
    expect(response.status()).toBe(200)
    taskId = (await response.json()).data.task_id
    expect(taskId).toMatch(/^job_[a-f0-9]{32}$/)
    await writeFile('../.local/quiz-browser.json', JSON.stringify({ taskId }) + '\n')
    const replay = await request.post('api/v1/quiz/generate/async', { headers: { ...headers,
      'Idempotency-Key': response.request().headers()['idempotency-key'] }, data: response.request().postDataJSON() })
    expect(replay.status()).toBe(200)
    expect((await replay.json()).data.task_id).toBe(taskId)
    await page.waitForURL(/pages\/quiz\/index\?taskId=/)
    await page.reload()
  }
  await expect(page.locator('.question-stem')).toBeVisible({ timeout: 75000 })
  const elapsed = Date.now() - started
  const task = await get(`learning/tasks/${taskId}`)
  expect(task.status).toBe('completed')
  expect(task.trace.model_calls).toBeGreaterThanOrEqual(1)
  expect(task.trace.model_calls).toBeLessThanOrEqual(4)
  expect(task.trace.tokens).toBeGreaterThan(0)
  expect(Object.keys(task.result).sort()).toEqual(['quiz_id', 'title'])
  const quizId = task.result.quiz_id
  const initial = await get(`user/quizzes/${quizId}`)
  expect(initial.questions).toHaveLength(5)
  expect(new Set(initial.questions.map(q => q.type))).toEqual(new Set(['single', 'multiple', 'judge']))
  if (!reuse) {
    expect(initial.questions.every(q => !('answer' in q) && !('explanation' in q) && !('citations' in q))).toBe(true)
    await page.locator('.answer-option').first().click()
    if (initial.questions[0].type === 'multiple') await page.locator('.answer-option').nth(1).click()
    const submitted = page.waitForResponse(response => response.url().endsWith(`/quiz/${quizId}/answer`))
    await page.getByText('确认答案', { exact: true }).click()
    expect((await submitted).status()).toBe(200)
  }
  await page.reload()
  const persisted = await get(`user/quizzes/${quizId}`)
  expect(persisted.answer_records).toHaveLength(1)
  expect(persisted.questions.slice(1).every(q => !('answer' in q))).toBe(true)
  await expect(page.getByText('已完成 1 题', { exact: false })).toBeVisible()
  await page.getByText('上一题', { exact: true }).click()
  await expect(page.locator('.answer-explanation')).toBeVisible()
  const first = persisted.questions[0], attempt = persisted.answer_records[0]
  expect(first.citations?.length).toBeGreaterThan(0)
  expect(first.citations.every(c => c.status === 'verified')).toBe(true)
  await page.locator('.quiz-citation .citation-link').first().click()
  await expect(page.locator('.original-content')).toContainText(first.citations[0].quote)
  await scrollTop()
  await page.screenshot({ path: '../docs/screenshots/h5/21-practice-source.png', fullPage: true })
  await page.getByText('返回', { exact: true }).click()
  await expect(page.getByText('第 2 / 5 题', { exact: false })).toBeVisible()
  await page.getByText('上一题', { exact: true }).click()
  expect(attempt.is_correct).toBe([...first.answer].sort().join(',') === [...attempt.selected_answers].sort().join(','))
  const repeated = await request.post(`api/v1/quiz/${quizId}/answer`, { headers,
    data: { question_id: first.id, selected_answers: attempt.selected_answers, duration_ms: 1 } })
  expect((await repeated.json()).data.replayed).toBe(true)
  await settle()
  await page.screenshot({ path: '../docs/screenshots/h5/22-cited-analysis.png', fullPage: true })
  await scrollTop()
  await page.screenshot({ path: '../docs/screenshots/h5/19-durable-practice.png', fullPage: true })
  await page.setViewportSize({ width: 320, height: 640 })
  await page.getByText('下一题', { exact: true }).click()
  await expect(page.getByText('第 2 / 5 题', { exact: false })).toBeVisible()
  expect(await page.locator('body').evaluate(node => node.scrollWidth <= window.innerWidth)).toBe(true)
  await page.getByText('上一题', { exact: true }).click()
  await page.setViewportSize({ width: 1440, height: 1000 })
  await scrollTop()
  await page.screenshot({ path: '../docs/screenshots/h5/20-practice-desktop.png', fullPage: true })
  expect(await page.locator('body').evaluate(node => node.scrollWidth <= window.innerWidth)).toBe(true)
  expect((await get('user/profile')).total_xp).toBe(before.total_xp)
  expect(errors).toEqual([])
  await writeFile(`../docs/evidence/m3-quiz-${reuse ? 'resume' : 'live'}.json`, JSON.stringify({
    recorded_at: new Date().toISOString(), source: 'Synthetic teaching document + real provider output, not real study data',
    environment: 'Chromium + isolated MySQL/Chroma + controlled worker', reuse_only: reuse, ui_ready_ms: elapsed,
    task_calls: task.trace.model_calls, returned_tokens: task.trace.tokens, unmetered_calls: task.trace.unmetered_calls || 0,
    question_count: 5, checks: [...(reuse ? [] : ['library_admission_and_idempotent_replay']), 'task_link_refresh', 'generic_task_answer_nondisclosure',
      'all_three_question_types', 'server_grading_and_repeat_submission', 'persisted_attempt_after_refresh', 'exact_quote_opens_source', '320px_answer_navigation', 'no_xp_without_report', 'no_browser_errors'],
    limitations: ['Exact quotes and fragment coverage do not prove semantic entailment',
      'Question semantics are not human rated', 'Legacy image and public-topic jobs are not yet durable',
      'Currency was not measured', 'No native WeChat execution'],
  }, null, 2) + '\n')
})
