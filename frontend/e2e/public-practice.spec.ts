import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { writeFile } from 'node:fs/promises'

test('public topic practice survives a lost admission response, refresh and cancellation', async ({ page, request }) => {
  const response = await request.post('api/v1/user/account/register', { data: { username: `e2e_public_${Date.now()}`, password: 'Local-E2E-Only-1976', nickname: '主题练习验收' } })
  expect(response.status()).toBe(200)
  const identity = (await response.json()).data
  const headers = { Authorization: `Bearer ${identity.token}` }
  const python = process.env.E2E_PYTHON || path.resolve('../backend/venv/Scripts/python.exe')
  const seed = (args: string[]) => execFileSync(python, [path.resolve('../scripts/seed_e2e.py'), '--user-id', String(identity.user.id), ...args], { encoding: 'utf8', windowsHide: true })
  const fixture = () => JSON.parse(seed(['--public-quiz-checkpoint']).split(/\r?\n/).find(line => line.startsWith('{'))!)
  const errors: string[] = [], ids: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  try {
    await page.goto('pages/login/index')
    await page.evaluate(user => {
      localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
      localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
    }, identity)
    const cancelled = fixture(); ids.push(cancelled.taskId)
    await page.goto(`pages/quiz/index?taskId=${cancelled.taskId}`)
    await page.getByText('取消练习', { exact: true }).click()
    await page.locator('.taro-model__confirm').click()
    await expect(page.getByText('练习任务已取消，未发布新题目', { exact: true })).toBeVisible()
    expect((await request.get(`api/v1/user/quizzes/${cancelled.quizId}`, { headers })).status()).toBe(404)

    const recovered = fixture(); ids.push(recovered.taskId)
    await page.goto('pages/index/index')
    await page.locator('textarea').fill(recovered.query)
    await page.getByRole('spinbutton', { name: '题目总数', exact: true }).fill('3')
    await expect(page.getByRole('spinbutton', { name: '单选题数量', exact: true })).toHaveValue('1')
    for (const width of [320, 390, 1440]) {
      await page.setViewportSize({ width, height: 844 })
      const geometry = await page.locator('.question-counts .count-input').evaluateAll(inputs => inputs.map(input => {
        const rect = input.getBoundingClientRect(), parent = input.parentElement!.getBoundingClientRect()
        const label = input.parentElement!.firstElementChild!.getBoundingClientRect()
        return { width: rect.width, right: rect.right, parentRight: parent.right, labelHeight: label.height }
      }))
      expect(geometry).toHaveLength(6)
      for (const rect of geometry) { expect(rect.width).toBeLessThanOrEqual(72); expect(rect.right).toBeLessThanOrEqual(rect.parentRight + 1); expect(rect.labelHeight).toBeLessThanOrEqual(30) }
    }
    await page.setViewportSize({ width: 390, height: 844 })
    await page.locator('.dashboard-grid .section-band').first().evaluate(element => element.scrollIntoView({ block: 'start' }))
    await page.screenshot({ path: '../docs/screenshots/h5/39-topic-practice-options.png', fullPage: true })
    const admissionKeys: string[] = []
    await page.route('**/quiz/generate/async', async route => {
      admissionKeys.push(route.request().headers()['idempotency-key'])
      const result = await route.fetch()
      expect(result.status()).toBe(200)
      expect((await result.json()).data.task_id).toBe(recovered.taskId)
      await route.abort('timedout')
    })
    await page.getByText('生成练习', { exact: true }).click()
    await expect(page.getByText('网络暂不可用，请检查连接后重试', { exact: true })).toBeVisible()
    const pendingKey = `ai-learn:v1:topic-practice:${identity.user.id}`
    const before = await page.evaluate(key => JSON.parse(localStorage.getItem(key)!).data, pendingKey)
    expect(before.key).toBe(admissionKeys[0])
    expect(before.taskId).toBeUndefined()
    expect(before.counts).toEqual({ single: 1, multiple: 1, judge: 1, fill: 0, written: 0 })
    await page.unroute('**/quiz/generate/async')
    page.on('request', req => { if (req.url().endsWith('/quiz/generate/async')) admissionKeys.push(req.headers()['idempotency-key']) })
    await page.reload()
    await expect(page.locator('textarea')).toHaveValue(recovered.query)
    await expect(page.locator('textarea')).toBeDisabled()
    await page.getByText('继续上次练习', { exact: true }).click()
    await expect(page.getByText('取消练习', { exact: true })).toBeVisible()
    expect(new Set(admissionKeys).size).toBe(1)
    await page.reload()
    await expect(page.getByText('取消练习', { exact: true })).toBeVisible()
    seed(['--release-quiz', recovered.taskId])
    await expect(page.locator('.question-stem')).toBeVisible({ timeout: 15000 })
    await expect(page.getByText('模型主题练习，未使用可核验的外部资料。解析可能有误，请对照教材。', { exact: true })).toBeVisible()
    const task = (await (await request.get(`api/v1/learning/tasks/${recovered.taskId}`, { headers })).json()).data
    expect(task.trace.model_calls).toBe(0)
    expect(Object.keys(task.result).sort()).toEqual(['quiz_id', 'title'])
    await page.screenshot({ path: '../docs/screenshots/h5/40-public-practice-recovered.png', fullPage: true })
    await page.goto('pages/index/index')
    await page.getByText('继续上次练习', { exact: true }).click()
    await expect(page.locator('.question-stem')).toBeVisible()
    expect(admissionKeys).toHaveLength(2)
    await page.goto('pages/index/index')
    await page.getByText('新一组练习', { exact: true }).click()
    await expect(page.locator('textarea')).toBeEnabled()
    expect(await page.evaluate(key => localStorage.getItem(key), pendingKey)).toBeNull()
    expect(errors).toEqual([])
    await writeFile('../docs/evidence/public-practice-ui.json', JSON.stringify({ recorded_at: new Date().toISOString(),
      environment: 'Chromium + actual local API + isolated MySQL + actual worker', data_source: 'Explicit synthetic checkpoint', provider_calls: 0,
      checks: ['cancel_without_publication', 'lost_admission_response_reuses_key', 'exact_counts_restored', 'refresh_resumes_worker', 'provenance_label', 'completed_task_reopens_without_new_admission', 'explicit_new_practice', 'no_browser_errors'],
      limitations: ['No native WeChat runtime verification', 'Separate paid smoke is required for provider integration'],
    }, null, 2) + '\n')
  } finally {
    for (const id of ids) await request.post(`api/v1/learning/tasks/${id}/cancel`, { headers })
  }
})

test('saved paid public practice renders with explicit web provenance on phone and desktop', async ({ page }) => {
  test.skip(process.env.AI_LEARN_PUBLIC_REUSE !== '1', 'Requires the bounded paid public smoke fixture; no new provider calls')
  const { readFile } = await import('node:fs/promises')
  const source = JSON.parse(await readFile('../.local/public-quiz-browser.json', 'utf8'))
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, source.account)
  await page.goto(`pages/quiz/index?quizId=${source.quizId}`)
  await expect(page.locator('.question-stem')).toBeVisible()
  await expect(page.getByText('网页仅作为出题参考，尚未完成逐题引用校验。', { exact: true })).toBeVisible()
  await expect(page.locator('.quiz-citation')).toHaveCount(0)
  await page.screenshot({ path: '../docs/screenshots/h5/41-live-public-practice.png', fullPage: true })
  for (const width of [320, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await expect(page.locator('.question-stem')).toBeVisible()
  }
})
