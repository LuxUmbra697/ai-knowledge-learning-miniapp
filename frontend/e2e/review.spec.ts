import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { writeFile } from 'node:fs/promises'

test('server-scheduled review, wrong answers, favorites and mastery persist across refresh', async ({ page, request }) => {
  test.setTimeout(60000)
  const registration = await request.post('api/v1/user/account/register', { data: { username: `e2e_review_${Date.now()}`, password: 'Local-E2E-Only-1976', nickname: '复习验收同学' } })
  expect(registration.status()).toBe(200)
  const identity = (await registration.json()).data, headers = { Authorization: `Bearer ${identity.token}` }
  const get = async (url: string) => {
    const response = await request.get(`api/v1/${url}`, { headers })
    expect(response.status()).toBe(200)
    return (await response.json()).data
  }
  const empty = await get('learning/summary')
  expect(empty.total_cards).toBe(0)
  expect(empty.concepts).toEqual([])
  const python = process.env.E2E_PYTHON || path.resolve('../backend/venv/Scripts/python.exe')
  execFileSync(python, [path.resolve('../scripts/seed_e2e.py'), '--user-id', String(identity.user.id), '--learning-review'], { encoding: 'utf8', windowsHide: true })
  const before = await get('learning/summary')
  expect(before.due_count).toBe(3)
  expect(before.today_reviews).toBe(0)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, identity)
  await page.goto('pages/index/index')
  await page.getByText('复习与掌握', { exact: true }).click()
  await expect(page.locator('.review-row')).toHaveCount(3)
  const initial = (await get('learning/cards?mode=due')).items
  expect(initial.every(card => !('answer' in card.question) && !('citations' in card.question))).toBe(true)
  await page.getByText('错题本', { exact: true }).click()
  await expect(page.locator('.review-row')).toHaveCount(1)
  await page.locator('.review-row').getByText('收藏', { exact: true }).click()
  await expect(page.getByText('取消收藏', { exact: true })).toBeVisible()
  await page.locator('.review-tabs').getByText('收藏', { exact: true }).click()
  await expect(page.locator('.review-row')).toHaveCount(1)
  const card = (await get('learning/cards?mode=favorites')).items[0]
  const confirmation = await request.put(`api/v1/learning/cards/${card.card_id}`, { headers, data: { diagnosis: 'careless' } })
  expect(confirmation.status()).toBe(200)
  for (const forged of [{ is_correct: true }, { user_id: identity.user.id + 1 }, { mastery: 1 }]) {
    expect((await request.post(`api/v1/learning/cards/${card.card_id}/answer`, { headers, data: { version: card.version, selected_answers: ['A'], ...forged } })).status()).toBe(422)
  }
  await page.reload()
  await expect(page.locator('.review-row')).toHaveCount(3)
  await expect(page.getByText('错因：粗心', { exact: false })).toBeVisible()
  await expect.poll(() => page.locator('body').evaluate(node => node.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: '../docs/screenshots/h5/07-review-plan.png', fullPage: true })
  await page.locator('.review-row').filter({ hasText: card.question.stem }).getByText('开始复习', { exact: true }).click()
  await expect(page.locator('.question-stem')).toBeVisible()
  await page.locator('.answer-option').first().click()
  let saved: any
  const answerRoute = `**/learning/cards/${card.card_id}/answer`
  await page.route(answerRoute, async route => {
    const response = await route.fetch()
    expect(response.status()).toBe(200)
    saved = (await response.json()).data
    await route.abort('connectionclosed')
  })
  await page.getByText('完成本次复习', { exact: true }).click()
  await expect(page.getByText('网络暂不可用，请检查连接后重试', { exact: true })).toBeVisible()
  await page.unroute(answerRoute)
  expect(saved.record.is_correct).toBe(true)
  expect(saved.version).toBe(2)
  await page.reload()
  await expect(page.getByText('这次记住了', { exact: true })).toBeVisible()
  await page.screenshot({ path: '../docs/screenshots/h5/23-review-analysis.png', fullPage: true })
  const after = await get('learning/summary')
  expect(after.today_reviews).toBe(1)
  expect(after.due_count).toBe(2)
  expect(after.concepts.reduce((n, c) => n + c.attempts, 0)).toBe(4)
  const replay = await request.post(`api/v1/learning/cards/${card.card_id}/answer`, { headers, data: { version: 1, selected_answers: ['A'] } })
  expect((await replay.json()).data.replayed).toBe(true)
  expect((await get('learning/summary')).today_reviews).toBe(1)
  await page.getByText('返回复习队列', { exact: true }).click()
  await page.getByText('掌握概况', { exact: true }).click()
  await expect(page.locator('.concept-row')).toHaveCount(3)
  await expect(page.locator('.trend-day')).toHaveCount(14)
  await page.screenshot({ path: '../docs/screenshots/h5/24-learning-progress.png', fullPage: true })
  await page.setViewportSize({ width: 320, height: 640 })
  expect(await page.locator('body').evaluate(node => node.scrollWidth <= window.innerWidth)).toBe(true)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await expect.poll(() => page.locator('body').evaluate(node => node.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: '../docs/screenshots/h5/25-learning-progress-desktop.png', fullPage: true })
  expect((await get('user/profile')).total_xp).toBe(0)
  expect(errors).toEqual([])
  await writeFile('../docs/evidence/m4-review-ui.json', JSON.stringify({ recorded_at: new Date().toISOString(),
    environment: 'Chromium + isolated MySQL + real API + FSRS 6.3.2; synthetic historical answers', provider_calls: 0,
    checks: ['cold_start', 'home_due_count', 'wrong_queue', 'favorite_persistence', 'confirmed_cause', 'no_answers_before_review',
      'forged_grading_fields_rejected', 'server_grading', 'FSRS_next_due', 'BKT_observation_count', 'result_restore', 'idempotent_review',
      'lost_response_recovery_without_duplicate_update', 'no_extra_XP', 'real_data_trend', '320_and_1440_width', 'no_browser_errors'],
    limitations: ['No personalization training or real learning-efficacy claim', 'Native WeChat execution pending'],
  }, null, 2) + '\n')
})
