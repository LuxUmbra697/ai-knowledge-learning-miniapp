import { test, expect } from '@playwright/test'

test('refresh is read-only, failed quiz has an explicit idempotent regeneration action', async ({ page, request }) => {
  const registered = await request.post('api/v1/user/account/register', { data: { username: `e2e_retry_${Date.now()}`, password: 'Local-E2E-Only-1976', nickname: '重试验收同学' } })
  expect(registered.status()).toBe(200)
  const identity = (await registered.json()).data
  const task = { task_id: 'job_synthetic_retry', kind: 'quiz', status: 'failed', stage: 'failed', title: '练习恢复验收',
    error_message: '生成内容未通过题目完整性校验，本轮尝试已结束，请点击“重新生成”再试', result: null,
    generation: { attempts: 10, max_attempts: 10 }, trace: { trace_id: 'synthetic', model_calls: 10, tokens: 100, nodes: [] } }
  let posts = 0
  await page.route('**/api/v1/learning/tasks', route => route.fulfill({ json: { code: 0, data: { items: [task] } } }))
  await page.route('**/api/v1/learning/tasks/job_synthetic_retry/retry', async route => {
    posts++
    expect(route.request().postDataJSON()).toEqual({})
    await new Promise(resolve => setTimeout(resolve, 250))
    await route.fulfill({ json: { code: 0, data: { ...task, task_id: 'job_synthetic_new', status: 'queued', stage: 'queued', error_message: null, generation: { attempts: 0, max_attempts: 10 } } } })
  })
  await page.route('**/api/v1/learning/tasks/job_synthetic_new', route => route.fulfill({ json: { code: 0, data: { ...task, task_id: 'job_synthetic_new', status: 'running', stage: 'quiz', error_message: null, generation: { attempts: 2, max_attempts: 10 } } } }))
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, identity)
  await page.goto('learning/tasks/index')
  await page.getByLabel('刷新任务', { exact: true }).click()
  await expect(page.getByText('任务已刷新', { exact: true })).toBeVisible()
  expect(posts).toBe(0)
  await expect(page.getByText('生成尝试 10 / 10', { exact: true })).toBeVisible()
  await page.getByText('重新生成', { exact: true }).click()
  await page.getByText('确定', { exact: true }).click()
  await expect(page).toHaveURL(/taskId=job_synthetic_new/)
  expect(posts).toBe(1)
  await expect(page.getByText('生成尝试 2 / 10', { exact: true })).toBeVisible()
  await page.setViewportSize({ width: 320, height: 720 })
  // Taro's navigation transition translates the page before it reaches its final position.
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.goto('learning/tasks/index')
  await page.screenshot({ path: '../.local/sdlc/quiz-retry/history-mobile.png', fullPage: true })
})
