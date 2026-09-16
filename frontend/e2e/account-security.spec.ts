import { test, expect } from '@playwright/test'

test('an unreachable login times out within 35 seconds and unlocks the form', async ({ page }) => {
  let release!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  await page.route('**/user/account/login', async route => { await pending; await route.abort() })
  try {
    await page.goto('pages/login/index')
    await page.locator('input[placeholder="字母、数字或 . _ -"]').fill('timeout_test')
    await page.locator('input[placeholder="至少 10 个字符"]').fill('Synthetic-Timeout-1976')
    await page.locator('.login-submit').click()
    await expect(page.locator('.notice')).toContainText('超时', { timeout: 35000 })
    await expect(page.locator('.login-submit')).toHaveJSProperty('disabled', false)
    await expect(page.locator('.login-submit')).toHaveText('进入学园')
  } finally { release() }
})

test('register, change password, recover and revoke old sessions through real API and MySQL', async ({ page, request }) => {
  const username = `e2e_identity_${Date.now()}`
  const first = 'Local-Identity-1976', second = 'Updated-Identity-1976', third = 'Recovered-Identity-1976'
  await page.goto('pages/login/index')
  await page.getByText('注册账号', { exact: true }).click()
  await page.locator('input[placeholder="你希望被怎样称呼"]').fill('账号联通验收')
  await page.locator('input[placeholder="字母、数字或 . _ -"]').fill(username)
  await page.locator('input[placeholder="至少 10 个字符"]').fill(first)
  const created = page.waitForResponse(response => response.url().endsWith('/user/account/register'))
  await page.getByText('开启我的学习旅程', { exact: true }).click()
  const identity = (await (await created).json()).data
  await expect(page.getByText('保存你的账号恢复码', { exact: true })).toBeVisible()
  await expect(page.locator('.recovery-code')).toHaveText(identity.recovery_code)
  await page.getByText('已保存，继续', { exact: true }).click()
  await page.goto('learning/security/index')
  await expect(page.locator('input[placeholder="字母、数字或 . _ -"]')).toHaveValue(username)
  await page.locator('input[placeholder="输入当前密码"]').fill(first)
  await page.locator('input[placeholder="至少 10 个字符"]').fill(second)
  await page.locator('input[placeholder="再次输入新密码"]').fill(second)
  const changed = page.waitForResponse(response => response.url().endsWith('/identity/credentials'))
  await page.getByText('保存账号密码', { exact: true }).click()
  const fresh = (await (await changed).json()).data
  await expect(page.locator('.recovery-code')).toHaveText(fresh.recovery_code)
  expect((await request.get('api/v1/user/profile', { headers: { Authorization: `Bearer ${identity.token}` } })).status()).toBe(401)
  await page.getByText('已保存，继续', { exact: true }).click()
  await page.goto('pages/profile/index')
  await page.getByText('退出登录', { exact: true }).click()
  await page.getByText('忘记密码', { exact: true }).click()
  await page.locator('input[placeholder="字母、数字或 . _ -"]').fill(username)
  await page.locator('input[placeholder="至少 10 个字符"]').fill(third)
  await page.locator('input[placeholder="再次输入新密码"]').fill(third)
  await page.locator('input[placeholder="注册或账号安全中保存的恢复码"]').fill(fresh.recovery_code)
  await page.getByText('重置密码', { exact: true }).click()
  await expect(page.getByText('密码已重置', { exact: true })).toBeVisible()
  await expect(page.locator('.account-success')).toContainText('原有设备的登录已失效')
  expect((await request.get('api/v1/user/profile', { headers: { Authorization: `Bearer ${fresh.token}` } })).status()).toBe(401)
  const repeated = await request.post('api/v1/user/identity/password/reset', { data: { username, password: first, recovery_code: fresh.recovery_code } })
  expect(repeated.status()).toBe(403)
  await page.locator('input[placeholder="至少 10 个字符"]').fill(third)
  await page.getByText('进入学园', { exact: true }).click()
  await expect(page).toHaveURL(/pages\/index\/index/)
  await page.goto('learning/security/index')
  await expect(page.locator('input[placeholder="字母、数字或 . _ -"]')).toHaveValue(username)
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: '../.local/sdlc/account-linking/security-mobile.png', fullPage: true })
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.screenshot({ path: '../.local/sdlc/account-linking/security-pc.png', fullPage: true })
})

test('H5 offers only available account authentication without requesting WeChat QR', async ({ page }) => {
  const requests: string[] = []
  page.on('request', request => { if (request.url().includes('/identity/qr/')) requests.push(request.url()) })
  await page.goto('pages/login/index')
  await expect(page.getByText('微信登录', { exact: true })).toHaveCount(0)
  await page.getByText('注册账号', { exact: true }).click()
  await expect(page.getByText('开启我的学习旅程', { exact: true })).toBeVisible()
  await page.getByText('账号登录', { exact: true }).click()
  await expect(page.getByText('进入学园', { exact: true })).toBeVisible()
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: `../.local/sdlc/account-linking/login-${width}.png`, fullPage: true })
  }
  expect(requests).toEqual([])
})
