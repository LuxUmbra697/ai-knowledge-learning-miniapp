import { test, expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'

test('saved paid companion dialogues show isolated memories, actions and story on phone and desktop', async ({ page }) => {
  test.skip(process.env.AI_LEARN_COMPANION_REUSE !== '1', 'Requires explicitly paid companion smoke; this browser test does not bill providers')
  const source = JSON.parse(await readFile('../.local/companion-browser.json', 'utf8'))
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, source.account)
  await page.goto('learning/companion/index?character=pink')
  await expect(page.locator('.room-turn')).toHaveCount(2)
  await expect(page.locator('.room-memory-used').first()).toContainText('例子')
  await expect(page.locator('.room-name')).toHaveText('樱野小满')
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: 960 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    expect(await page.locator('.room-composer .primary-button').evaluate(element => {
      const a = element.getBoundingClientRect(), b = element.parentElement!.getBoundingClientRect()
      return a.left >= b.left - 1 && a.right <= b.right + 1
    })).toBeTruthy()
    await expect.poll(() => page.locator('.room-portrait img').evaluate(img => (img as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
    expect(await page.locator('.room-portrait img').evaluate(img => {
      const a = img.getBoundingClientRect(), b = img.parentElement!.getBoundingClientRect()
      return a.left >= b.left - 2 && a.right <= b.right + 2 && a.bottom <= b.bottom + 2
    })).toBeTruthy()
    if (width === 390) expect(await page.locator('.room-composer .primary-button').evaluate(element => {
      const button = element.getBoundingClientRect(), nav = document.querySelector('.mobile-navigation')!.getBoundingClientRect()
      return button.bottom < nav.top && button.top >= 0
    })).toBeTruthy()
    if (width !== 320) await page.screenshot({ path: `../docs/screenshots/h5/52-companion-chat-${width}.png`, fullPage: true })
  }
  await page.getByText('秋庭澄', { exact: true }).first().click()
  await expect(page.locator('.room-turn')).toHaveCount(1)
  await expect(page.locator('.room-memory-used')).toContainText('简短具体')
  await page.setViewportSize({ width: 390, height: 960 })
  await page.screenshot({ path: '../docs/screenshots/h5/53-companion-orange.png', fullPage: true })
  const portrait = page.locator('.room-portrait')
  await portrait.click()
  await expect(portrait).toHaveClass(/emotion-happy/)
  await page.locator('.room-tabs').getByText('记忆 1', { exact: true }).click()
  await expect(page.locator('.room-memory-row')).toHaveCount(1)
  await expect(page.locator('.room-memory-row')).toContainText('喜欢简短具体的提醒')
  expect(errors).toEqual([])
})
