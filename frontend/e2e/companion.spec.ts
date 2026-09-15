import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { writeFile } from 'node:fs/promises'

test('companion remains discoverable on focus pages and safely folds in crowded viewports', async ({ page, request }) => {
  const registered = await request.post('api/v1/user/account/register', { data: {
    username: `e2e_buddy_${Date.now()}`, password: 'Local-E2E-Only-1976', nickname: '伙伴验收同学',
  } })
  expect(registered.status()).toBe(200)
  const identity = (await registered.json()).data
  execFileSync(process.env.E2E_PYTHON || path.resolve('../backend/venv/Scripts/python.exe'),
    [path.resolve('../scripts/seed_e2e.py'), '--user-id', String(identity.user.id), '--learning-review'], { windowsHide: true })
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, identity)
  await page.goto('learning/review/index')
  await page.getByText('开始复习', { exact: true }).first().click()
  await expect(page.locator('.question-stem')).toBeVisible()
  // Regression: focus previously unmounted the partner entirely.
  await expect(page.locator('.companion-dock')).toBeVisible()
  await expect(page.locator('.companion-dock')).toHaveAttribute('data-state', 'folded')
  await expect.poll(() => page.locator('.companion-dock img').evaluate(img => (img as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
  await page.getByLabel('展开学习伙伴', { exact: true }).click()
  await expect(page.locator('.companion-reserved .companion-portrait')).toBeVisible()
  expect(await page.locator('.companion-reserved .companion-portrait img').evaluate(img => {
    const image = img.getBoundingClientRect(), host = img.parentElement!.getBoundingClientRect()
    return image.left >= host.left - 6 && image.right <= host.right + 6 && image.bottom <= host.bottom + 6
  })).toBeTruthy()
  expect(await page.locator('.companion-reserved').evaluate(buddy => {
    const a = buddy.getBoundingClientRect()
    return [...document.querySelectorAll('.answer-option, .practice-navigation')].every(node => {
      const b = node.getBoundingClientRect()
      return a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom
    })
  })).toBeTruthy()
  await page.screenshot({ path: '../docs/screenshots/h5/26-companion-focus.png', fullPage: true })
  await page.getByLabel('收起学习伙伴', { exact: true }).click()
  await page.reload()
  await expect(page.locator('.companion-dock')).toHaveAttribute('data-state', 'folded')
  await page.getByLabel('展开学习伙伴', { exact: true }).click()
  await page.setViewportSize({ width: 320, height: 330 })
  await page.goto('pages/index/index')
  await expect(page.locator('.companion-dock')).toBeVisible()
  await expect(page.locator('.companion')).toBeHidden()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await page.setViewportSize({ width: 1440, height: 1000 })
  await expect(page.locator('.companion')).toBeVisible()
  await page.getByLabel('外观设置', { exact: true }).click()
  await page.locator('.setting-row').filter({ hasText: /^学习伙伴$/ }).locator('input').uncheck()
  await page.getByLabel('关闭外观设置').click()
  await expect(page.locator('.companion')).toHaveCount(0)
  await expect(page.getByLabel('显示学习伙伴', { exact: true })).toBeVisible()
  await page.reload()
  await page.getByLabel('显示学习伙伴', { exact: true }).click()
  await expect(page.locator('.companion')).toBeVisible()
  await writeFile('../docs/evidence/companion-visibility.json', JSON.stringify({
    recorded_at: new Date().toISOString(), runtime: 'Chromium, real local API and isolated synthetic answers', provider_calls: 0,
    checks: ['focus_visible_dock', 'portrait_asset_loaded', 'expanded_reserved_space', 'no_answer_overlap', 'fold_restore',
      'crowded_viewport_fallback', 'resize_recovery', 'hide_persist_and_restore'], native: 'Build only; runtime verification pending',
  }, null, 2) + '\n')
})
