import { test, expect } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'

test('painted scenes load with correct media types and keep forms and documents readable', async ({ page, request }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await mkdir('../docs/screenshots/h5', { recursive: true })
  await page.goto('pages/login/index')
  const scene = page.locator('.academy-background img')
  await expect(scene).toHaveAttribute('src', 'https://ai-knowledge-learn.oss-cn-guangzhou.aliyuncs.com/assets/academy-gate.jpg')
  await expect(scene).toBeVisible()
  await expect.poll(() => scene.evaluate(e => (e as HTMLImageElement).naturalWidth)).toBe(1280)
  const asset = await request.get(await scene.getAttribute('src') as string)
  expect(asset.headers()['content-type']).toBe('image/jpeg')
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await expect(page.getByText('进入学园', { exact: true })).toBeVisible()
    expect(await page.locator('.login-form').evaluate(e => getComputedStyle(e).backgroundColor)).toBe('rgb(255, 255, 255)')
    const bounds = await scene.boundingBox()
    expect(Math.round(bounds!.width)).toBe(width)
    await page.screenshot({ path: `../docs/screenshots/h5/29-login-${width}.png`, fullPage: true })
  }
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByLabel('外观设置', { exact: true }).click()
  await page.locator('.theme-option').filter({ hasText: '月夜观测室' }).click()
  await page.getByLabel('关闭外观设置').click()
  expect(await page.locator('.login-form').evaluate(e => getComputedStyle(e).backgroundColor)).toBe('rgb(41, 50, 52)')
  await page.screenshot({ path: '../docs/screenshots/h5/30-login-night.png', fullPage: true })
  await page.getByLabel('外观设置', { exact: true }).click()
  await page.locator('.theme-option').filter({ hasText: '樱花学园' }).click()
  await page.getByLabel('关闭外观设置').click()
  const response = await request.post('api/v1/user/account/register', { data: {
    username: `e2e_art_${Date.now()}`, password: 'Local-E2E-Only-1976', nickname: '书架验收同学',
  } })
  expect(response.status()).toBe(200)
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, (await response.json()).data)
  await page.goto('pages/knowledge/index')
  const shelf = page.locator('.shelf-panorama img')
  await expect.poll(() => shelf.evaluate(e => (e as HTMLImageElement).naturalWidth)).toBe(1200)
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await expect(page.getByText('添加学习材料', { exact: true })).toBeVisible()
    expect(await shelf.evaluate(e => getComputedStyle(e).objectFit)).toBe('contain')
    expect(await shelf.evaluate(e => {
      const image = e.getBoundingClientRect(), upload = document.querySelector('.upload-band')!.getBoundingClientRect()
      return image.bottom <= upload.top + 1
    })).toBeTruthy()
    await page.screenshot({ path: `../docs/screenshots/h5/31-library-${width}.png`, fullPage: true })
  }
  expect(errors).toEqual([])
  await writeFile('../docs/evidence/artwork-ui.json', JSON.stringify({ recorded_at: new Date().toISOString(),
    environment: 'Chromium + real local API + isolated MySQL', provider_calls: 0,
    widths: [320, 390, 1440], checks: ['jpeg_mime', 'actual_decoded_dimensions', 'opaque_login_form',
      'night_theme', 'uncropped_shelf', 'upload_visible', 'no_horizontal_overflow', 'no_page_errors'],
    native_runtime: 'Not assessed by this H5 test; see separate native evidence in oss-delivery.json',
  }, null, 2) + '\n')
})
