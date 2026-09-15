import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { writeFile } from 'node:fs/promises'

test('create named notebooks and explicitly collect wrong questions from answers and reports', async ({ page, request }) => {
  test.setTimeout(60000)
  const register = async (suffix: string) => {
    const response = await request.post('api/v1/user/account/register', { data: { username: `e2e_books_${suffix}_${Date.now()}`, password: 'Local-E2E-Only-1976', nickname: '错题归档同学' } })
    expect(response.status()).toBe(200)
    return (await response.json()).data
  }
  const identity = await register('owner'), other = await register('other')
  const headers = { Authorization: `Bearer ${identity.token}` }, otherHeaders = { Authorization: `Bearer ${other.token}` }
  execFileSync(process.env.E2E_PYTHON || path.resolve('../backend/venv/Scripts/python.exe'),
    [path.resolve('../scripts/seed_e2e.py'), '--user-id', String(identity.user.id), '--learning-review'], { windowsHide: true })
  const get = async (url: string) => { const response = await request.get(`api/v1/${url}`, { headers }); expect(response.status()).toBe(200); return (await response.json()).data }
  const card = (await get('learning/cards?mode=wrong')).items[0]
  expect((await get('learning/notebooks')).items).toEqual([])
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, identity)
  await page.goto('learning/review/index')
  await page.getByText('错题本', { exact: true }).click()
  await page.getByText('新建错题本', { exact: true }).click()
  await page.getByRole('textbox', { name: '错题本名称' }).fill('学习方法')
  await page.getByText('创建错题本', { exact: true }).click()
  await expect(page.locator('.notebook-selector')).toHaveText('学习方法')
  await expect(page.locator('.review-row')).toHaveCount(0)
  const first = (await get('learning/notebooks')).items[0]
  expect(first.question_count).toBe(0)
  await page.goto(`pages/quiz/index?quizId=${card.quiz_id}`)
  await expect(page.getByText('再理解一次', { exact: true })).toBeVisible()
  for (let i = 0; i < 2; i++) {
    await page.getByText('加入错题本', { exact: true }).click()
    await page.locator('.notebook-destination').filter({ hasText: '学习方法' }).click()
    await expect(page.locator('.notebook-dialog')).toHaveCount(0)
  }
  expect((await get('learning/notebooks')).items[0].question_count).toBe(1)
  await page.goto(`pages/report/index?quizId=${card.quiz_id}`)
  await page.getByText('加入错题本', { exact: true }).click()
  await page.getByRole('textbox', { name: '错题本名称' }).fill('面试复盘')
  expect(await page.locator('.notebook-destination').getByText('学习方法', { exact: true }).evaluate(e =>
    getComputedStyle(e).color !== getComputedStyle(e.closest('.notebook-dialog')!).backgroundColor)).toBeTruthy()
  expect(await page.locator('.notebook-destination').getByText('学习方法', { exact: true }).evaluate(e => getComputedStyle(e).color)).toBe('rgb(48, 64, 57)')
  await page.screenshot({ path: '../docs/screenshots/h5/27-notebook-destination.png' })
  await page.getByText('新建并加入', { exact: true }).click()
  await expect(page.locator('.notebook-dialog')).toHaveCount(0)
  expect((await get('learning/notebooks')).items.map(b => b.question_count)).toEqual([1, 1])
  expect((await request.get(`api/v1/learning/notebooks/${first.notebook_id}/cards`, { headers: otherHeaders })).status()).toBe(404)
  expect((await request.put(`api/v1/learning/notebooks/${first.notebook_id}/cards/${card.card_id}`, { headers: otherHeaders })).status()).toBe(404)
  expect((await request.post('api/v1/learning/notebooks', { headers, data: { name: '伪造身份', user_id: other.user.id } })).status()).toBe(422)
  await page.goto('learning/review/index')
  await page.getByText('错题本', { exact: true }).click()
  await page.locator('.notebook-selector').click()
  const choice = page.locator('.weui-picker__item').filter({ hasText: '学习方法 (1)' })
  await expect(choice).toBeVisible()
  await expect.poll(() => page.locator('.weui-picker').filter({ visible: true }).evaluate(e => Math.round(e.getBoundingClientRect().bottom))).toBe(page.viewportSize()!.height)
  const box = (await choice.boundingBox())!
  // The picker mask owns pointer gestures; click its displayed row, as a user would.
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2)
  await page.locator('.weui-picker__action').getByText('确定', { exact: true }).filter({ visible: true }).click()
  await expect(page.locator('.notebook-selector')).toHaveText('学习方法')
  await expect(page.locator('.review-row')).toHaveCount(1)
  await page.getByText('重命名', { exact: true }).click()
  await page.getByRole('textbox', { name: '错题本名称' }).fill('学习方法 · 第一章')
  await page.getByText('保存名称', { exact: true }).click()
  await expect(page.locator('.notebook-selector')).toHaveText('学习方法 · 第一章')
  await expect.poll(() => page.locator('.companion').evaluate(e => {
    if (getComputedStyle(e).visibility === 'hidden') return true
    const a = e.getBoundingClientRect(), b = document.querySelector('.notebook-toolbar')!.getBoundingClientRect()
    return a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom
  })).toBeTruthy()
  await page.screenshot({ path: '../docs/screenshots/h5/28-error-notebook.png', fullPage: true })
  await page.getByText('从此本移除', { exact: true }).click()
  await expect(page.locator('.review-row')).toHaveCount(0)
  expect((await get('learning/cards?mode=wrong')).items).toHaveLength(1)
  await page.getByText('删除错题本', { exact: true }).click()
  await page.getByText('确定', { exact: true }).filter({ visible: true }).click()
  await expect(page.locator('.notebook-selector')).toHaveText('全部错题')
  await expect(page.locator('.review-row')).toHaveCount(1)
  expect((await get('learning/notebooks')).items).toHaveLength(1)
  const summary = await get('learning/summary')
  expect(summary.concepts.reduce((n, c) => n + c.attempts, 0)).toBe(3)
  for (const width of [320, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  }
  expect(errors).toEqual([])
  await writeFile('../docs/evidence/notebooks-ui.json', JSON.stringify({ recorded_at: new Date().toISOString(),
    environment: 'Chromium + isolated MySQL + real API; synthetic questions', provider_calls: 0,
    checks: ['empty_named_notebook', 'explicit_add_after_answer', 'idempotent_add', 'create_and_add_from_report',
      'cross_user_denial', 'forged_user_rejected', 'native_Taro_picker_interaction_in_H5', 'rename', 'remove_membership_only',
      'delete_confirmation', 'learning_observations_unchanged', 'mobile_and_desktop_layout', 'no_page_errors'], native_runtime: 'Pending IDE access',
  }, null, 2) + '\n')
})
