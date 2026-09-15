import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { writeFile } from 'node:fs/promises'

test('explicit reading checklist persists without changing learning or review dates', async ({ page, request }) => {
  const response = await request.post('api/v1/user/account/register', { data: { username: `e2e_read_${Date.now()}`, password: 'Local-E2E-Only-1976', nickname: '阅读验收同学' } })
  expect(response.status()).toBe(200)
  const user = (await response.json()).data, headers = { Authorization: `Bearer ${user.token}` }
  const output = execFileSync(process.env.E2E_PYTHON || path.resolve('../backend/venv/Scripts/python.exe'),
    [path.resolve('../scripts/seed_e2e.py'), '--user-id', String(user.user.id)], { windowsHide: true, encoding: 'utf8' })
  const quizId = output.match(/^quiz_e2e_[a-f0-9]{12}/m)?.[0]
  expect(quizId).toBeTruthy()
  expect((await request.post(`api/v1/quiz/${quizId}/answer`, { headers, data: { question_id: 'q1', selected_answers: ['B'] } })).status()).toBe(200)
  const cards = async () => (await (await request.get('api/v1/learning/cards?mode=all', { headers })).json()).data.items
  const before = await cards()
  await page.goto('pages/login/index')
  await page.evaluate(identity => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: identity.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: identity.user }))
  }, user)
  await page.goto('learning/path/index')
  await expect(page.locator('.plan-item')).toHaveCount(1)
  await expect(page.locator('.plan-item .tag')).toContainText('阅读')
  await page.getByText('确认本轮计划', { exact: true }).click()
  await page.locator('.taro-model__confirm').click()
  await page.getByText('已阅读', { exact: true }).click()
  await page.locator('.taro-model__confirm').click()
  await expect(page.getByText('你已确认阅读', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('你已确认阅读', { exact: true })).toBeVisible()
  expect(await cards()).toEqual(before)
  const colors = await page.getByText('重新安排', { exact: true }).evaluate(node => {
    const probe = document.createElement('span'); probe.style.color = 'var(--accent)'; node.parentElement!.appendChild(probe)
    const result = { actual: getComputedStyle(node).color, expected: getComputedStyle(probe).color }; probe.remove(); return result
  })
  expect(colors.actual).toBe(colors.expected)
  await page.screenshot({ path: '../docs/screenshots/h5/50-confirmed-reading.png', fullPage: true })
  await writeFile('../docs/evidence/plan-reading-ui.json', JSON.stringify({ recorded_at: new Date().toISOString(),
    data_source: 'Explicit synthetic wrong answer, actual local API and MySQL', provider_calls: 0,
    checks: ['not_due_reading_suggestion', 'explicit_plan_confirmation', 'explicit_read_confirmation', 'refresh_persistence', 'unchanged_mastery_card_version_due_date'],
  }, null, 2) + '\n')
})
