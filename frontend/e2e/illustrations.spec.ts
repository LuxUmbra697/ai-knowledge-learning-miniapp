import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { readFile, writeFile } from 'node:fs/promises'

test('image cancellation and recovered failure preserve text practice without provider calls', async ({ page, request }) => {
  const response = await request.post('api/v1/user/account/register', { data: { username: `e2e_images_${Date.now()}`, password: 'Local-E2E-Only-1976', nickname: '配图验收' } })
  expect(response.status()).toBe(200)
  const identity = (await response.json()).data
  const headers = { Authorization: `Bearer ${identity.token}` }, ids: string[] = [], errors: string[] = []
  const python = process.env.E2E_PYTHON || path.resolve('../backend/venv/Scripts/python.exe')
  const seed = (args: string[] = []) => execFileSync(python, [path.resolve('../scripts/seed_images_e2e.py'), '--user-id', String(identity.user.id), ...args], { encoding: 'utf8', windowsHide: true })
  const fixture = () => JSON.parse(seed().split(/\r?\n/).find(line => line.startsWith('{'))!)
  page.on('pageerror', error => errors.push(error.message))
  try {
    await page.goto('pages/login/index')
    await page.evaluate(user => {
      localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
      localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
    }, identity)
    const cancelled = fixture(); ids.push(cancelled.taskId)
    await page.goto(`pages/quiz/index?quizId=${cancelled.quizId}`)
    await expect(page.locator('.question-stem')).toBeVisible()
    await page.getByText('取消配图', { exact: true }).click()
    await page.locator('.taro-model__confirm').click()
    await expect(page.getByText('配图未完成，文字练习不受影响', { exact: true })).toBeVisible()
    expect((await (await request.get(`api/v1/learning/tasks/${cancelled.taskId}`, { headers })).json()).data.status).toBe('cancelled')
    await page.reload()
    await expect(page.locator('.question-stem')).toBeVisible()
    const answer = page.locator('.answer-option').filter({ hasText: '应当保留，可以继续作答' })
    await answer.click()
    await expect(answer).toHaveAttribute('aria-pressed', 'true')
    await page.getByText('确认答案', { exact: true }).click()
    await expect(page.getByText('配图任务独立于已保存的文字题库。', { exact: true })).toBeVisible()
    const recovered = fixture(); ids.push(recovered.taskId)
    await page.goto(`pages/quiz/index?quizId=${recovered.quizId}`)
    await expect(page.getByText('取消配图', { exact: true })).toBeVisible()
    seed(['--release', recovered.taskId])
    await expect(page.getByText('配图未完成，文字练习不受影响', { exact: true })).toBeVisible({ timeout: 15000 })
    expect(await page.locator('.illustration-frame').evaluate(element => element.getBoundingClientRect().height)).toBeLessThanOrEqual(100)
    for (const id of ids) {
      const task = (await (await request.get(`api/v1/learning/tasks/${id}`, { headers })).json()).data
      expect(task.trace.model_calls).toBe(0)
    }
    await page.screenshot({ path: '../docs/screenshots/h5/43-image-failure-text-preserved.png', fullPage: true })
    await page.goto('pages/index/index')
    let polls = 0
    page.on('request', req => { if (req.url().includes('/quiz/images/')) polls++ })
    await page.waitForTimeout(3000)
    expect(polls).toBe(0)
    expect(errors).toEqual([])
    await writeFile('../docs/evidence/quiz-image-ui.json', JSON.stringify({ recorded_at: new Date().toISOString(),
      environment: 'Chromium + actual API + isolated MySQL + actual worker', data_source: 'Explicit synthetic image checkpoints', provider_calls: 0,
      checks: ['cancel_retains_quiz', 'refresh_and_server_scoring', 'restart_checkpoint_failure', 'leave_page_stops_polling', 'no_browser_errors'],
      limitations: ['No native WeChat runtime verification'],
    }, null, 2) + '\n')
  } finally { for (const id of ids) await request.post(`api/v1/learning/tasks/${id}/cancel`, { headers }) }
})

test('saved paid illustration renders a private image on mobile and desktop', async ({ page }) => {
  test.skip(process.env.AI_LEARN_IMAGE_REUSE !== '1', 'Requires the bounded paid image smoke; reuses the saved image without new model calls')
  const source = JSON.parse(await readFile('../.local/image-quiz-browser.json', 'utf8'))
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, source.account)
  await page.goto(`pages/quiz/index?quizId=${source.quizId}`)
  const bitmap = page.locator('.question-media img')
  await expect(bitmap).toBeVisible()
  await expect.poll(() => bitmap.evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth > 0)).toBeTruthy()
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    const geometry = await page.locator('.illustration-frame').evaluate(element => {
      const frame = element.getBoundingClientRect(), image = element.querySelector('img')!.getBoundingClientRect()
      return { frameWidth: frame.width, frameHeight: frame.height, imageWidth: image.width, imageHeight: image.height, inside: image.left >= frame.left && image.right <= frame.right + 1 && image.top >= frame.top && image.bottom <= frame.bottom + 1 }
    })
    expect(geometry.inside).toBeTruthy()
    expect(geometry.imageHeight).toBeGreaterThan(100)
    expect(geometry.frameHeight).toBeLessThanOrEqual(386)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  }
  await page.setViewportSize({ width: 390, height: 1000 })
  await page.screenshot({ path: '../docs/screenshots/h5/42-live-private-illustration.png', fullPage: true })
  await expect(page.getByText('AI 示意图 · 非答案证据', { exact: true })).toBeVisible()
})
