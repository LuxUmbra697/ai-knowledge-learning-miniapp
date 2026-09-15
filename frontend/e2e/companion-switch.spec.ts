import { test, expect } from '@playwright/test'

test('character selection clears old content immediately and late responses cannot restore it', async ({ page, request }) => {
  const response = await request.post('api/v1/user/account/register', { data: {
    username: `e2e_switch_${Date.now()}`, password: 'Local-E2E-Only-1976', nickname: '角色切换验收',
  } })
  expect(response.status()).toBe(200)
  const identity = (await response.json()).data
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
    localStorage.setItem('ai-learn:v1:appearance', JSON.stringify({ data: { companionForm: 'orange' } }))
  }, identity)
  await page.goto('learning/companion/index?character=pink')
  await expect(page.locator('.room-name')).toHaveText('樱野小满')
  await expect(page.locator('.companion-dock img')).toHaveAttribute('src', /companion-pink/)
  const portraitFits = async () => {
    const host = (await page.locator('.room-portrait > taro-image-core').boundingBox())!
    const image = (await page.locator('.room-portrait img').boundingBox())!
    expect(image.x).toBeGreaterThanOrEqual(host.x - 1)
    expect(image.y).toBeGreaterThanOrEqual(host.y - 1)
    expect(image.x + image.width).toBeLessThanOrEqual(host.x + host.width + 1)
    expect(image.y + image.height).toBeLessThanOrEqual(host.y + host.height + 1)
  }
  await portraitFits()
  let release = () => {}
  const delayed = new Promise<void>(resolve => { release = resolve })
  let intercepted = false
  await page.route('**/api/v1/companions/orange', async route => {
    intercepted = true
    const actual = await route.fetch()
    await delayed
    await route.fulfill({ response: actual })
  })
  await page.locator('.room-character-tabs').getByText('秋庭澄', { exact: true }).click()
  await expect(page.locator('.room-character-tabs')).toHaveAttribute('data-character', 'orange')
  await expect(page.locator('.room-name')).toHaveCount(0)
  await expect(page.getByText('正在翻开伙伴手札', { exact: true })).toBeVisible()
  await expect.poll(() => intercepted).toBe(true)
  await page.locator('.room-character-tabs').getByText('樱野小满', { exact: true }).click()
  await expect(page.locator('.room-name')).toHaveText('樱野小满')
  release()
  await page.waitForTimeout(300)
  await expect(page.locator('.room-name')).toHaveText('樱野小满')
  await page.unroute('**/api/v1/companions/orange')
  await page.locator('.room-character-tabs').getByText('秋庭澄', { exact: true }).click()
  await expect(page.locator('.room-name')).toHaveText('秋庭澄')
  await portraitFits()
  await expect(page.locator('.companion-room')).toHaveClass(/room-orange/)
  await expect(page.locator('.companion-dock img')).toHaveAttribute('src', /companion-orange/)
  await expect(page).toHaveURL(/character=orange/)
  await page.reload()
  await expect(page.locator('.room-name')).toHaveText('秋庭澄')
  await page.screenshot({ path: '../docs/screenshots/h5/60-character-switch-mobile.png', fullPage: true })
  await page.getByLabel('外观设置', { exact: true }).click()
  await page.getByLabel('粉樱学妹', { exact: true }).click()
  await expect(page.locator('.appearance-dialog')).toHaveCount(0)
  await expect(page.locator('.room-name')).toHaveText('樱野小满')
  await expect(page.locator('.companion-dock img')).toHaveAttribute('src', /companion-pink/)
  await expect(page).toHaveURL(/character=pink/)
})
