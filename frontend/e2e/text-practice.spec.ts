import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { writeFile } from 'node:fs/promises'

test('five types preserve drafts, grade server-side and recover written assessment without new calls', async ({ page, request }) => {
  const identity = (await (await request.post('api/v1/user/account/register', { data: { username: `e2e_text_${Date.now()}`, password: 'Local-E2E-Only-1976', nickname: '五题型验收同学' } })).json()).data
  const headers = { Authorization: `Bearer ${identity.token}` }
  const seed = (args: string[] = []) => execFileSync(process.env.E2E_PYTHON || path.resolve('../backend/venv/Scripts/python.exe'), [path.resolve('../scripts/seed_text_e2e.py'), '--user-id', String(identity.user.id), ...args], { encoding: 'utf8', windowsHide: true })
  const fixture = JSON.parse(seed().split(/\r?\n/).find(line => line.startsWith('{'))!)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  try {
    await page.goto('pages/login/index')
    await page.evaluate(user => {
      localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
      localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
    }, identity)
    await page.goto('pages/index/index')
    await page.locator('input[aria-label="题目总数"]').fill('10')
    for (const label of ['单选题', '多选题', '判断题', '填空题', '问答题']) await page.locator(`input[aria-label="${label}数量"]`).fill('1')
    await expect(page.locator('input[aria-label="题目总数"]')).toHaveValue('5')
    await page.locator('.question-counts').scrollIntoViewIfNeeded()
    await page.screenshot({ path: '../docs/screenshots/h5/32-question-blueprint.png', fullPage: true })
    await page.goto(`pages/quiz/index?quizId=${fixture.quizId}`)
    const before = (await (await request.get(`api/v1/user/quizzes/${fixture.quizId}`, { headers })).json()).data
    expect(before.questions.every(q => !('answer' in q) && !('rubric' in q) && !('accepted_answers' in q))).toBeTruthy()
    expect(before.questions[3].blank_count).toBe(2)
    for (const choices of [[0], [0, 1], [1]]) {
      for (const option of choices) await page.locator('.answer-option').nth(option).click()
      await page.getByText('确认答案', { exact: true }).click()
      await expect(page.getByText('回答正确', { exact: true })).toBeVisible()
      await page.getByText('下一题', { exact: true }).click()
    }
    await page.getByRole('textbox', { name: '第 1 空答案' }).fill('提取')
    await page.getByRole('textbox', { name: '第 2 空答案' }).fill('页数')
    await page.reload()
    await expect(page.getByRole('textbox', { name: '第 1 空答案' })).toHaveValue('提取')
    await page.getByText('确认答案', { exact: true }).click()
    await expect(page.getByText('再理解一次', { exact: true })).toBeVisible()
    await page.screenshot({ path: '../docs/screenshots/h5/33-fill-analysis.png', fullPage: true })
    await page.getByText('下一题', { exact: true }).click()
    await page.getByRole('textbox', { name: '问答题答案' }).fill('主动提取记忆，检验理解。')
    await page.getByText('确认答案', { exact: true }).click()
    await expect(page.getByText('取消评阅', { exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByText('取消评阅', { exact: true })).toBeVisible()
    seed(['--release', fixture.taskId])
    await expect(page.getByText('回答正确', { exact: true })).toBeVisible({ timeout: 15000 })
    await expect(page.locator('.grading-feedback')).toContainText('要点 2')
    await page.locator('.grading-feedback').scrollIntoViewIfNeeded()
    await page.screenshot({ path: '../docs/screenshots/h5/34-written-assessment.png', fullPage: true })
    const detail = (await (await request.get(`api/v1/user/quizzes/${fixture.quizId}`, { headers })).json()).data
    expect(detail.answer_records).toHaveLength(5)
    expect(detail.answer_records.find(item => item.question_id === 'q4').grading.blank_matches).toEqual([true, false])
    const job = (await (await request.get(`api/v1/learning/tasks/${fixture.taskId}`, { headers })).json()).data
    expect(job.status).toBe('completed')
    expect(job.trace.model_calls).toBe(0)
    for (const width of [320, 1440]) {
      await page.setViewportSize({ width, height: 900 })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    }
    expect(errors).toEqual([])
    await writeFile('../docs/evidence/text-practice-ui.json', JSON.stringify({ recorded_at: new Date().toISOString(),
      provider_calls: 0, source: 'Synthetic questions and persisted synthetic grading response; real API/MySQL/worker/Chromium',
      checks: ['per_type_counts', 'five_question_types', 'answer_and_rubric_disclosure', 'ordered_fill_grading', 'draft_restore', 'written_task_restore', 'criteria_rendering', 'five_authoritative_attempts', 'mobile_desktop_bounds'], native_runtime: 'Pending',
    }, null, 2) + '\n')
  } finally {
    try { await request.delete(`api/v1/learning/tasks/${fixture.taskId}`, { headers }) }
    catch { test.info().annotations.push({ type: 'cleanup', description: 'Request context closed; synthetic checkpoint remains isolated and cannot call a provider.' }) }
  }
})

test('saved real five-type output renders the actual paid rubric assessment', async ({ page }) => {
  test.skip(process.env.AI_LEARN_TEXT_REUSE !== '1', 'Requires the explicit paid smoke fixture; this browser test makes no provider calls')
  const { readFile } = await import('node:fs/promises')
  const source = JSON.parse(await readFile('../.local/text-quiz-browser.json', 'utf8'))
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, source.account)
  await page.goto(`pages/quiz/index?quizId=${source.quizId}`)
  for (let index = 0; index < 5; index++) {
    if (await page.locator('.written-answer').count()) break
    await page.getByText('下一题', { exact: true }).click()
  }
  await expect(page.locator('.written-answer')).toBeVisible()
  await expect(page.locator('.grading-feedback')).toContainText('模型按要点评阅')
  await page.locator('.grading-feedback').scrollIntoViewIfNeeded()
  await page.screenshot({ path: '../docs/screenshots/h5/35-live-written-assessment.png', fullPage: true })
  await page.setViewportSize({ width: 1440, height: 1500 })
  await page.locator('.page-title').scrollIntoViewIfNeeded()
  await page.screenshot({ path: '../docs/screenshots/h5/36-live-written-desktop.png', fullPage: true })
})
