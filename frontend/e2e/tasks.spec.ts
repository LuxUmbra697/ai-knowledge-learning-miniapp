import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import path from 'node:path'

test('owned task history cancels an interrupted upload and persists after reload', async ({ page, request }) => {
  const response = await request.post('api/v1/user/account/register', { data: { username: `e2e_jobs_${Date.now()}`, password: 'Local-E2E-Only-1976', nickname: '任务验收同学' } })
  expect(response.status()).toBe(200)
  const identity = (await response.json()).data
  const python = process.env.E2E_PYTHON || path.resolve('../backend/venv/Scripts/python.exe')
  const output = execFileSync(python, [path.resolve('../scripts/seed_e2e.py'), '--user-id', String(identity.user.id), '--staged-upload'], { encoding: 'utf8', windowsHide: true })
  const taskId = output.trim().split(/\r?\n/).find(line => line.startsWith('job_'))!
  expect(taskId).toBeTruthy()
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, identity)
  await page.goto('pages/profile/index')
  await page.getByText('任务记录', { exact: true }).click()
  await expect(page.locator('.task-entry')).toHaveCount(1)
  await expect(page.getByText('等待上传完成', { exact: true })).toBeVisible()
  await page.getByText('取消任务', { exact: true }).click()
  await page.getByText('确定', { exact: true }).click()
  await expect(page.getByText('已取消', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('已取消', { exact: true })).toBeVisible()
  await page.getByText('执行记录', { exact: true }).click()
  await expect(page.getByText('外部调用 0 次', { exact: false })).toBeVisible()
  await page.setViewportSize({ width: 320, height: 720 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: '../docs/screenshots/h5/13-task-history.png', fullPage: true })
  const headers = { Authorization: `Bearer ${identity.token}` }
  const state = (await (await request.get(`api/v1/learning/tasks/${taskId}`, { headers })).json()).data
  expect(state.status).toBe('cancelled')
  expect(state.trace.model_calls).toBe(0)
  expect(state).not.toHaveProperty('payload_json')
  expect(state).not.toHaveProperty('lease_token')
  const other = (await (await request.post('api/v1/user/account/register', { data: { username: `e2e_stranger_${Date.now()}`, password: 'Local-E2E-Only-1976' } })).json()).data
  expect((await request.get(`api/v1/learning/tasks/${taskId}`, { headers: { Authorization: `Bearer ${other.token}` } })).status()).toBe(404)
  expect((await request.post(`api/v1/learning/tasks/${taskId}/cancel`, { headers: { Authorization: `Bearer ${other.token}` } })).status()).toBe(404)
})
