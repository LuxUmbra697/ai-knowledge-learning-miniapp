import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { writeFile } from 'node:fs/promises'

test('owned plans connect actual reviews, prerequisite editing and immutable history', async ({ page, request }) => {
  test.setTimeout(60000)
  const register = async () => (await (await request.post('api/v1/user/account/register', { data: {
    username: `e2e_plan_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`, password: 'Local-E2E-Only-1976', nickname: '路径验收同学',
  } })).json()).data
  const identity = await register(), other = await register(), headers = { Authorization: `Bearer ${identity.token}` }
  const get = async (url: string) => {
    const result = await request.get(`api/v1/learning/${url}`, { headers })
    expect(result.status()).toBe(200)
    return (await result.json()).data
  }
  expect((await get('plans/preview')).items).toEqual([])
  execFileSync(process.env.E2E_PYTHON || path.resolve('../backend/venv/Scripts/python.exe'),
    [path.resolve('../scripts/seed_e2e.py'), '--user-id', String(identity.user.id), '--learning-review'], { windowsHide: true })
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, identity)
  await page.goto('pages/index/index')
  await page.getByText('学习路径与计划', { exact: true }).click()
  await expect(page.locator('.plan-item')).toHaveCount(3)
  await expect(page.locator('.plan-item').getByText('开始这项复习', { exact: true })).toHaveCount(0)
  await page.locator('.primary-button').filter({ hasText: '确认本轮计划' }).click()
  await page.locator('.taro-model__cancel').click()
  expect((await get('plans')).items).toEqual([])
  await page.locator('.primary-button').filter({ hasText: '确认本轮计划' }).click()
  await page.locator('.taro-model__confirm').click()
  await expect(page.getByText(/已确认计划/)).toBeVisible()
  await expect(page.getByText('重新安排', { exact: true })).toBeEnabled()
  const plans = (await get('plans')).items, id = plans[0].plan_id, before = await get(`plans/${id}`)
  expect(plans).toHaveLength(1)
  expect((await request.get(`api/v1/learning/plans/${id}`, { headers: { Authorization: `Bearer ${other.token}` } })).status()).toBe(404)
  expect((await request.get(`api/v1/learning/cards/${before.items[0].card_id}`, { headers: { Authorization: `Bearer ${other.token}` } })).status()).toBe(404)
  expect((await request.put(`api/v1/learning/plans/${id}/read/${before.items[0].id}`, { headers })).status()).toBe(422)
  await page.screenshot({ path: '../docs/screenshots/h5/48-confirmed-study-plan.png', fullPage: true })
  await page.locator('.plan-item').first().getByText('开始这项复习', { exact: true }).click()
  await expect(page.locator('.question-stem')).toBeVisible()
  const card = await get(`cards/${before.items[0].card_id}`)
  await expect(page.locator('.question-stem')).toHaveText(card.question.stem)
  expect(card.question.answer).toBeUndefined()
  await page.locator('.answer-option').first().click()
  await page.getByText('完成本次复习', { exact: true }).click()
  await expect(page.locator('.answer-explanation')).toBeVisible()
  await page.goto(`learning/path/index?planId=${id}`)
  await expect(page.locator('.plan-item[data-completed=true]')).toHaveCount(1)
  expect((await get(`plans/${id}`)).items[0].completion_source).toBe('server_review_event')
  await page.getByText('前置关系', { exact: true }).click()
  await page.getByText('添加关系', { exact: true }).click()
  await page.locator('.taro-model__confirm').click()
  await expect(page.locator('.path-edge')).toHaveCount(1)
  await expect(page.locator('.map-image')).toBeVisible()
  expect(await page.locator('.map-image').evaluate(img => (img as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
  const relations = await get('path'), [a, b] = relations.edges[0]
  expect((await request.put('api/v1/learning/path', { headers, data: { version: relations.version, edges: [[a, b], [b, a]] } })).status()).toBe(422)
  expect((await request.put('api/v1/learning/path', { headers: { Authorization: `Bearer ${other.token}` }, data: { version: 0, edges: [[a, b]] } })).status()).toBe(422)
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  }
  await page.setViewportSize({ width: 390, height: 1000 })
  await page.screenshot({ path: '../docs/screenshots/h5/49-prerequisite-path.png', fullPage: true })
  await page.getByText('本轮计划', { exact: true }).click()
  await expect(page.getByText('关系或日期已变化。这是原计划记录，可以重新安排。', { exact: true })).toBeVisible()
  await page.getByText('重新安排', { exact: true }).click()
  await expect(page.getByText('前置条件待巩固', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText(/已确认计划/)).toBeVisible()
  expect((await get('plans')).items).toHaveLength(1)
  expect(errors).toEqual([])
  await writeFile('../docs/evidence/learning-plans-ui.json', JSON.stringify({ recorded_at: new Date().toISOString(),
    environment: 'Chromium + actual API + isolated MySQL', data_source: 'Explicit synthetic historical attempts', provider_calls: 0,
    checks: ['cold_start', 'preview_without_mutation', 'declined_confirmation', 'owned_immutable_plan', 'actual_review_deep_link',
      'no_manual_review_completion', 'server_event_completion', 'explicit_prerequisite_edit', 'cycle_rejection', 'cross_owner_rejection',
      'real_mermaid_diagram', 'stale_path_notice', 'history_refresh', '320_390_1440_bounds', 'no_browser_errors'],
    limitations: ['Policy time estimates and default BKT parameters, not student learning efficacy', 'Native runtime remains unverified'],
  }, null, 2) + '\n')
})
