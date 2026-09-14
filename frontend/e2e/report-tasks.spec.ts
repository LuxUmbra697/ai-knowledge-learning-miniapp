import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { writeFile } from 'node:fs/promises'

test('report cancellation and checkpoint recovery use real API persistence without model calls', async ({ page, request }) => {
  const register = await request.post('api/v1/user/account/register', { data: { username: `e2e_reports_${Date.now()}`, password: 'Local-E2E-Only-1976', nickname: '报告验收同学' } })
  expect(register.status()).toBe(200)
  const identity = (await register.json()).data
  const headers = { Authorization: `Bearer ${identity.token}` }
  const python = process.env.E2E_PYTHON || path.resolve('../backend/venv/Scripts/python.exe')
  const seed = (args: string[]) => execFileSync(python, [path.resolve('../scripts/seed_e2e.py'), '--user-id', String(identity.user.id), ...args], { encoding: 'utf8', windowsHide: true })
  const seeded: string[] = []
  const fixture = () => {
    const item = JSON.parse(seed(['--report-checkpoint']).split(/\r?\n/).find(line => line.startsWith('{'))!)
    seeded.push(item.taskId)
    return item
  }
  const get = async (url: string) => {
    const response = await request.get(`api/v1/${url}`, { headers })
    expect(response.status()).toBe(200)
    return (await response.json()).data
  }
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  try {
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, identity)
  const openPending = async (item: { quizId: string; taskId: string }) => {
    await page.evaluate(({ item, userId }) => localStorage.setItem(`ai-learn:v1:report:${userId}:${item.quizId}`, JSON.stringify({ data: { key: 'test-report-key', taskId: item.taskId } })), { item, userId: identity.user.id })
    await page.goto(`pages/report/index?quizId=${item.quizId}`)
    await expect(page.getByText('取消报告', { exact: true })).toBeVisible()
    const action = await page.locator('.section-band .primary-button').boundingBox()
    const cancel = await page.getByText('取消报告', { exact: true }).boundingBox()
    expect(cancel!.x - (action!.x + action!.width)).toBeGreaterThanOrEqual(8)
  }
  const cancelled = fixture()
  await openPending(cancelled)
  await page.getByText('取消报告', { exact: true }).click()
  await page.getByText('确定', { exact: true }).click()
  await expect(page.getByText('报告任务已取消，作答记录仍然保留', { exact: true })).toBeVisible()
  expect((await get(`learning/tasks/${cancelled.taskId}`)).status).toBe('cancelled')
  expect((await get('user/profile')).total_xp).toBe(0)
  expect((await get(`user/quizzes/${cancelled.quizId}`)).report).toBeNull()

  const recovered = fixture()
  await openPending(recovered)
  await page.reload()
  await expect(page.getByText('取消报告', { exact: true })).toBeVisible()
  await page.screenshot({ path: '../docs/screenshots/h5/14-report-task.png', fullPage: true })
  await page.evaluate(({ userId, quizId }) => localStorage.removeItem(`ai-learn:v1:report:${userId}:${quizId}`), { userId: identity.user.id, quizId: recovered.quizId })
  await page.goto('learning/tasks/index')
  await page.locator('.task-entry').filter({ has: page.getByText('取消任务', { exact: true }) }).getByText('查看报告', { exact: true }).click()
  await expect(page.getByText('取消报告', { exact: true })).toBeVisible()
  seed(['--release-report', recovered.taskId])
  await expect(page.getByText('这是一份合成验收报告。', { exact: true })).toBeVisible({ timeout: 15000 })
  await page.reload()
  await expect(page.getByText('这是一份合成验收报告。', { exact: true })).toBeVisible()
  const state = await get(`learning/tasks/${recovered.taskId}`)
  expect(state.status).toBe('completed')
  expect(state.trace.model_calls).toBe(0)
  expect(state.trace.nodes.map(node => node.stage)).toContain('report_validated')
  expect((await get('user/profile')).total_xp).toBe(16)
  const replay = await request.post('api/v1/report/generate/async', { headers, data: { quiz_id: recovered.quizId } })
  expect((await replay.json()).data.task_id).toBe(recovered.taskId)
  expect((await get('user/profile')).total_xp).toBe(16)
  await page.goto('learning/tasks/index')
  await page.getByText('查看报告', { exact: true }).first().click()
  await expect(page.getByText('这是一份合成验收报告。', { exact: true })).toBeVisible()
  expect(errors).toEqual([])
  await writeFile('../docs/evidence/m3-report-task-ui.json', JSON.stringify({
    recorded_at: new Date().toISOString(), source: 'Explicit synthetic saved-response checkpoint, not a live model result',
    environment: 'Chromium + local API + isolated MySQL + actual worker', provider_calls: 0,
    checks: ['cancel_preserves_answers_without_xp_or_report', 'refresh_resumes_pending_task', 'worker_revalidates_saved_response',
      'atomic_report_xp_completion', 'different_key_reuses_completed_task', 'task_history_links_report', 'pending_report_resumes_without_local_reference', 'no_browser_errors'],
    limitations: ['No native WeChat execution', 'This fixture does not rate model output quality'],
  }, null, 2) + '\n')
  } finally {
    for (const taskId of seeded) await request.post(`api/v1/learning/tasks/${taskId}/cancel`, { headers })
  }
})
