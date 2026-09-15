import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { writeFile } from 'node:fs/promises'
import path from 'node:path'

test('completed practice has real Mermaid maps, explicit wrong review and resilient source loading', async ({ page, request }) => {
  const identity = (await (await request.post('api/v1/user/account/register', { data: { username: `e2e_map_${Date.now()}`, password: 'Local-E2E-Only-1976', nickname: '梳理图验收同学' } })).json()).data
  const headers = { Authorization: `Bearer ${identity.token}` }
  const seeded = execFileSync(process.env.E2E_PYTHON || path.resolve('../backend/venv/Scripts/python.exe'), [path.resolve('../scripts/seed_e2e.py'), '--user-id', String(identity.user.id), '--learning-review'], { encoding: 'utf8', windowsHide: true })
  const fixture = JSON.parse(seeded.split(/\r?\n/).find(line => line.startsWith('{'))!)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, identity)
  await page.goto(`pages/report/index?quizId=${fixture.quizId}`)
  const image = page.locator('.map-image')
  await expect(image).toBeVisible()
  await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0)
  const svgText = () => image.evaluate(async (img: HTMLImageElement) => new DOMParser().parseFromString(await (await fetch(img.src)).text(), 'image/svg+xml').documentElement.textContent || '')
  await expect.poll(svgText).toContain('主动回忆')
  expect(await svgText()).not.toContain('&#20027;')
  const map = (await (await request.get(`api/v1/quiz/${fixture.quizId}/maps`, { headers })).json()).data
  expect(map.nodes.filter(n => n.state === 'wrong')).toHaveLength(1)
  await page.getByText('错题复盘', { exact: true }).click()
  await expect(page.locator('.map-node-list')).toContainText('第 1 题')
  await expect(page.locator('.map-node-list')).not.toContainText('第 2 题')
  await expect(page.getByText('未完成复盘', { exact: true })).toHaveCount(0)
  await page.getByText('关系网络', { exact: true }).click()
  await expect(image).toBeVisible()
  await page.locator('.map-node-list').getByText('查看作答解析', { exact: true }).nth(1).click()
  await expect(page.locator('.question-stem')).toContainText('哪些记录可以帮助回顾')
  await page.goto(`pages/report/index?quizId=${fixture.quizId}`)
  await expect(image).toBeVisible()
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    await page.locator('.learning-map').scrollIntoViewIfNeeded()
    await page.waitForTimeout(250)
    const partnerElement = page.locator('.companion')
    const partner = await partnerElement.isVisible() ? await partnerElement.boundingBox() : null
    const controls = await page.locator('.map-toolbar').boundingBox()
    if (partner && controls) expect(partner.x + partner.width <= controls.x || controls.x + controls.width <= partner.x || partner.y + partner.height <= controls.y || controls.y + controls.height <= partner.y).toBeTruthy()
    else await expect(page.locator('.companion-dock')).toBeAttached()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await page.screenshot({ path: `../docs/screenshots/h5/37-study-map-${width}.png`, fullPage: true })
  }
  const before = map.source_hash
  await page.reload()
  await expect(image).toBeVisible()
  expect((await (await request.get(`api/v1/quiz/${fixture.quizId}/maps`, { headers })).json()).data.source_hash).toBe(before)
  await page.route('**/quiz/*/maps', route => route.fulfill({ status: 503, json: { code: 5030, message: '梳理图读取暂不可用' } }))
  await page.reload()
  await expect(page.getByText('梳理图读取暂不可用', { exact: true })).toBeVisible()
  await expect(page.getByText('作答与解析', { exact: true })).toBeVisible()
  await page.unroute('**/quiz/*/maps')
  await page.locator('.learning-map').getByText('重试', { exact: true }).click()
  await expect(image).toBeVisible()
  const hostile = { ...map, nodes: map.nodes.map(n => ({ ...n, label: n.id === 'root' ? '<img onerror=alert(1)>' : n.label })) }
  await page.route('**/quiz/*/maps', route => route.fulfill({ status: 200, json: { code: 0, data: hostile } }))
  const dialogs: string[] = []
  page.on('dialog', dialog => { dialogs.push(dialog.message()); void dialog.dismiss() })
  await page.reload()
  await expect(image).toBeVisible()
  const safeSvg = await image.evaluate(async (img: HTMLImageElement) => new DOMParser().parseFromString(await (await fetch(img.src)).text(), 'image/svg+xml').documentElement.outerHTML)
  expect(safeSvg).not.toMatch(/<(?:script|image|foreignObject|iframe|a)[\s>]/i)
  expect(dialogs).toEqual([])
  await page.unroute('**/quiz/*/maps')
  const detail = (await (await request.get(`api/v1/user/quizzes/${fixture.quizId}`, { headers })).json()).data
  await page.route('**/user/quizzes/*', route => route.fulfill({ status: 200, json: { code: 0, data: { ...detail, report: { three_line_summary: ['合成空薄弱点报告'], weak_points: [], advice: [] } } } }))
  await page.reload()
  await expect(page.getByText('报告尚未归纳薄弱点，请结合下方错题解析复习。', { exact: true })).toBeVisible()
  await expect(page.getByText('本次练习未发现错误，后续复习仍有助于保持记忆。', { exact: true })).toHaveCount(0)
  await page.unroute('**/user/quizzes/*')
  expect(errors).toEqual([])
  await writeFile('../docs/evidence/study-maps-ui.json', JSON.stringify({ recorded_at: new Date().toISOString(),
    provider_calls: 0, source: 'Synthetic saved answers, real local API/MySQL/Mermaid/Chromium',
    checks: ['completed_answer_map', 'wrong_question_filter', 'network_view', 'refresh_stable_hash', 'loading_failure_keeps_analysis', 'retry', '320_390_1440_bounds', 'decoded_svg_image', 'readable_chinese_svg_labels', 'question_deep_link', 'untrusted_labels_cannot_create_active_svg'],
    native_runtime: 'Separate IDE verification; this receipt covers H5 only',
  }, null, 2) + '\n')
})

test('saved paid practice renders original-source network without another provider call', async ({ page }) => {
  test.skip(process.env.AI_LEARN_TEXT_REUSE !== '1', 'Requires the existing bounded live fixture')
  const { readFile } = await import('node:fs/promises')
  const source = JSON.parse(await readFile('../.local/text-quiz-browser.json', 'utf8'))
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, source.account)
  await page.goto(`pages/report/index?quizId=${source.quizId}`)
  await page.getByText('关系网络', { exact: true }).click()
  await expect(page.locator('.map-image')).toBeVisible()
  await expect(page.locator('.map-node-list').getByText('查看原文', { exact: true }).first()).toBeVisible()
  await page.setViewportSize({ width: 1440, height: 1400 })
  await page.locator('.learning-map').scrollIntoViewIfNeeded()
  await page.screenshot({ path: '../docs/screenshots/h5/38-live-evidence-network.png', fullPage: true })
  await page.locator('.map-node-list').getByText('查看原文', { exact: true }).first().click()
  await expect(page.locator('.original-content')).not.toHaveCount(0)
})
