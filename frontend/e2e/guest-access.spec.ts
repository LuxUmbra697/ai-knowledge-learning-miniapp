import { test, expect } from '@playwright/test'

test('anonymous visitors can browse home and decline login without private requests', async ({ page }) => {
  const privateRequests: string[] = []
  page.on('request', req => { if (req.url().includes('/api/v1/')) privateRequests.push(new URL(req.url()).pathname) })
  await page.goto('pages/index/index')
  await expect(page.locator('.page-title')).toHaveText('学习手帐')
  await expect(page.locator('.guest-browse')).toBeVisible()
  await expect(page.locator('.home-tools')).toBeVisible()
  await page.getByText('复习与掌握', { exact: true }).click()
  await expect(page.getByText('登录后继续', { exact: true })).toBeVisible()
  await page.getByText('继续浏览', { exact: true }).click()
  await expect(page).toHaveURL(/pages\/index\/index/)
  await page.locator('.mobile-nav-item').filter({ hasText: '学习档案' }).click()
  await page.getByText('去登录', { exact: true }).click()
  await expect(page.locator('.login-switch')).toBeVisible()
  await page.getByText('先逛逛学园', { exact: true }).click()
  await expect(page.locator('.guest-browse')).toBeVisible()
  expect(privateRequests).toEqual([])
})

test('H5 has only usable account choices and a public privacy page', async ({ page }) => {
  await page.goto('pages/login/index')
  await expect(page.locator('.login-switch')).toContainText('账号登录')
  await expect(page.locator('.login-switch')).toContainText('注册账号')
  await expect(page.getByText('微信登录', { exact: true })).toHaveCount(0)
  await page.getByText('忘记密码', { exact: true }).click()
  await expect(page.getByText('改用已绑定微信验证', { exact: true })).toHaveCount(0)
  await page.getByText('隐私说明', { exact: true }).click()
  await expect(page.locator('.page-title:visible')).toHaveText('隐私说明')
  await expect(page.locator('.privacy-content')).toContainText('我们不会索取你的手机号、通讯录、位置或微信头像。')
})

test('a private deep link preserves its identifier across login and can be declined', async ({ page }) => {
  const privateRequests: string[] = []
  page.on('request', request => { if (request.url().includes('/api/v1/')) privateRequests.push(request.url()) })
  await page.goto('learning/document/index?docId=guest_document_123')
  await page.getByText('继续浏览', { exact: true }).click()
  await expect(page.locator('.guest-browse')).toBeVisible()
  expect(privateRequests).toEqual([])
  await page.goto('learning/document/index?docId=guest_document_123')
  await page.getByText('去登录', { exact: true }).click()
  await expect(page.locator('.login-switch')).toBeVisible()
  const pending = await page.evaluate(() => JSON.parse(localStorage.getItem('ai-learn:v1:login-return') || '{}').data)
  expect(pending.path).toBe('/learning/document/index?docId=guest_document_123')
  expect(privateRequests).toEqual([])
})

test('guest protected action returns to its destination only after real account login', async ({ page, request }) => {
  const username = `e2e_guest_${Date.now()}`, password = 'Synthetic-Guest-1976'
  expect((await request.post('api/v1/user/account/register', { data: { username, password, nickname: '访客验收' } })).status()).toBe(200)
  await page.goto('pages/index/index')
  await page.locator('.mobile-nav-item').filter({ hasText: '知识书架' }).click()
  await page.getByText('去登录', { exact: true }).click()
  await expect(page.locator('.login-switch')).toBeVisible()
  await page.locator('input[placeholder="字母、数字或 . _ -"]').fill(username)
  await page.locator('input[placeholder="至少 10 个字符"]').fill(password)
  await page.getByText('进入学园', { exact: true }).click()
  await expect(page).toHaveURL(/pages\/knowledge\/index/)
  await expect(page.getByText('添加学习材料', { exact: true })).toBeVisible()
})
