import { test, expect, Page } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'

const themes = ['sakura', 'night', 'sea', 'forest', 'scroll']
const cleanLayout = { contrast: [], clipping: [], occlusion: [], overflow: false }

export async function inspectLayout(page: Page) {
  return page.locator('.studio').evaluate(root => {
    const rgb = (value: string) => {
      const parts = value.match(/[\d.]+/g)!.map(Number)
      return [parts[0], parts[1], parts[2], parts[3] ?? 1]
    }
    const blend = (front: number[], back: number[]) => front.slice(0, 3).map((c, i) => c * front[3] + back[i] * (1 - front[3])).concat(1)
    const luminance = (color: number[]) => color.slice(0, 3).map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0)
    const background = (element: Element | null): number[] => {
      if (!element) return [255, 255, 255, 1]
      const color = rgb(getComputedStyle(element).backgroundColor)
      return color[3] === 1 ? color : blend(color, background(element.parentElement))
    }
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
    const contrast: object[] = [], clipping: object[] = [], occlusion: string[] = []
    const buddy = root.querySelector('.companion')
    const buddyBox = buddy?.checkVisibility({ checkVisibilityCSS: true }) ? buddy.getBoundingClientRect() : null
    let node: Node | null
    while ((node = walker.nextNode())) {
      const text = node.textContent?.trim(), element = node.parentElement
      if (!text || !element || !element.checkVisibility({ checkVisibilityCSS: true, checkOpacity: true })) continue
      const rect = element.getBoundingClientRect(), style = getComputedStyle(element)
      if (!rect.width || !rect.height || element.closest('.tooltip, .map-viewport')) continue
      if (buddyBox && !element.closest('.companion') && rect.bottom > 0 && rect.top < innerHeight) {
        const range = document.createRange(); range.selectNodeContents(node)
        if ([...range.getClientRects()].some(line => line.right > buddyBox.left && line.left < buddyBox.right && line.bottom > buddyBox.top && line.top < buddyBox.bottom)) occlusion.push(text.slice(0, 70))
      }
      // Disabled controls are checked separately for behavior. WCAG exempts inactive text.
      if (!element.closest('[disabled]:not([disabled="false"]),button:disabled,.page-heading') && Number(style.opacity) === 1) {
        const back = background(element), fore = blend(rgb(style.color), back)
        const a = luminance(fore), b = luminance(back), ratio = (Math.max(a, b) + .05) / (Math.min(a, b) + .05)
        const large = parseFloat(style.fontSize) >= 24 || (parseFloat(style.fontSize) >= 18.66 && parseInt(style.fontWeight) >= 700)
        if (ratio < (large ? 3 : 4.5)) contrast.push({ text: text.slice(0, 70), class: element.className, color: style.color, background: back, ratio })
      }
      if (element.closest('.map-node-list, .room-transcript')) continue
      const range = document.createRange(); range.selectNodeContents(node)
      const parent = element.closest('taro-button-core,button,.studio-input,.tag')
      if (parent) {
        const box = parent.getBoundingClientRect()
        for (const line of range.getClientRects()) {
          if (line.left < box.left - 1 || line.right > box.right + 1 || line.top < box.top - 2 || line.bottom > box.bottom + 2) {
            clipping.push({ text: text.slice(0, 70), class: parent.className }); break
          }
        }
      }
    }
    return { contrast, clipping, occlusion, overflow: document.documentElement.scrollWidth > innerWidth + 1 }
  })
}

test('all login choices retain readable colors before and after switching, in every theme', async ({ page }) => {
  for (const theme of themes) {
    await page.goto('pages/login/index')
    await page.evaluate(theme => localStorage.setItem('ai-learn:v1:appearance', JSON.stringify({ data: { theme, reducedMotion: true } })), theme)
    await page.reload()
    await expect(page.locator(`.theme-${theme}`)).toBeVisible()
    for (const width of [320, 390, 1440]) {
      await page.setViewportSize({ width, height: 900 })
      for (const label of ['账号登录', '微信登录', '注册账号']) {
        await page.locator('.login-switch').getByText(label, { exact: true }).click()
        const metrics = await inspectLayout(page)
        expect(metrics, `${theme} ${width} ${label}`).toEqual(cleanLayout)
      }
      await page.getByText('忘记密码', { exact: true }).click()
      expect(await inspectLayout(page), `${theme} ${width} recovery`).toEqual(cleanLayout)
    }
  }
})

test('busy login retains its label and prevents duplicate submission', async ({ page }) => {
  let requests = 0
  let release!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  await page.route('**/user/account/login', async route => {
    requests++
    await pending
    await route.fulfill({ status: 401, json: { detail: '账号或密码不正确' } })
  })
  await page.goto('pages/login/index')
  await page.locator('input').nth(0).fill('layout_test')
  await page.locator('input').nth(1).fill('Synthetic-Only-123')
  await page.locator('.login-submit').click()
  await expect(page.locator('.login-submit')).toHaveJSProperty('disabled', true)
  await expect(page.locator('.login-submit')).toHaveText('正在提交')
  expect(await page.locator('.login-submit').evaluate(el => getComputedStyle(el).color)).toBe('rgb(255, 255, 255)')
  expect(await page.locator('.login-submit').evaluate(el => getComputedStyle(el).opacity)).toBe('0.55')
  await page.locator('.login-submit').dispatchEvent('click')
  expect(requests).toBe(1)
  release()
  await expect(page.getByText('账号或密码不正确', { exact: true })).toBeVisible()
  await expect(page.locator('.login-submit')).toHaveJSProperty('disabled', false)
  expect(await page.locator('.login-submit').evaluate(el => getComputedStyle(el).opacity)).toBe('1')
  expect(await inspectLayout(page)).toEqual(cleanLayout)
})

for (const width of (process.env.LAYOUT_ALL_WIDTHS === '1' ? [320, 390, 768, 1440, 1920] : [390, 1440])) {
  test(`all configured pages and common panels remain readable at ${width}px`, async ({ page, request }) => {
    test.setTimeout(240000)
    const identity = (await (await request.post('api/v1/user/account/register', { data: {
      username: `e2e_layout_${Date.now()}`, password: 'Synthetic-Only-123', nickname: '学习布局验收同学',
    } })).json()).data
    const seed = (script: string, args: string[] = []) => {
      const output = execFileSync(process.env.E2E_PYTHON || path.resolve('../backend/venv/Scripts/python.exe'),
        [path.resolve('../scripts/' + script), '--user-id', String(identity.user.id), ...args], { encoding: 'utf8', windowsHide: true })
      return JSON.parse(output.split(/\r?\n/).find(line => line.startsWith('{'))!)
    }
    const fixture = { ...seed('seed_e2e.py', ['--learning-review']), ...seed('seed_layout_e2e.py') }
    await page.setViewportSize({ width, height: 900 })
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    await page.goto('pages/login/index')
    await page.evaluate(identity => {
      localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: identity.token }))
      localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: identity.user }))
      localStorage.setItem('ai-learn:v1:appearance', JSON.stringify({ data: { reducedMotion: true } }))
    }, identity)
    const routes = [
      ['login', 'pages/login/index', '.login-switch'],
      ['home', 'pages/index/index', '.history-row'],
      ['knowledge', 'pages/knowledge/index', '.document-row'],
      ['quiz', `pages/quiz/index?quizId=${fixture.quizId}`, '.answer-explanation'],
      ['report', `pages/report/index?quizId=${fixture.quizId}`, '.map-image'],
      ['profile', 'pages/profile/index', '.profile-form input'],
      ['assistant', 'learning/assistant/index', '.source-choice'],
      ['document', `learning/document/index?docId=${fixture.docId}`, '.original-content'],
      ['tasks', 'learning/tasks/index', '.task-entry'],
      ['review', 'learning/review/index', '.review-row'],
      ['tutor', 'learning/tutor/index', '.tutor-setup'],
      ['path', 'learning/path/index', '.plan-item'],
      ['companion', 'learning/companion/index', '.room-greeting'],
      ['security', 'learning/security/index', '.security-summary'],
    ]
    const directory = path.resolve(`../.local/sdlc/layout-audit/${width}`)
    await mkdir(directory, { recursive: true })
    const results: object[] = []
    const inspect = async (name: string) => {
      await page.waitForTimeout(180)
      const metrics = await inspectLayout(page)
      results.push({ name, ...metrics })
      await page.screenshot({ path: path.join(directory, name + '.png'), fullPage: true })
      if (!name.includes('appearance') && !name.includes('dialog')) {
        const scroller = page.locator('.taro_page').last()
        if (await scroller.count()) {
          const original = await scroller.evaluate(el => { const top = el.scrollTop; el.scrollTop = el.scrollHeight; return top })
          await page.waitForTimeout(180)
          const bottom = await inspectLayout(page)
          results.push({ name: name + '-bottom', ...bottom })
          expect.soft(bottom, `${width}px ${name} bottom`).toEqual(cleanLayout)
          await page.screenshot({ path: path.join(directory, name + '-bottom.png') })
          await scroller.evaluate((el, top) => { el.scrollTop = top }, original)
        }
      }
      await writeFile(path.join(directory, 'results.json'), JSON.stringify(results, null, 2))
      expect.soft(metrics, `${width}px ${name}`).toEqual(cleanLayout)
    }
    for (const [name, url, ready] of routes) {
      await page.goto(url)
      await expect(page.locator(ready).first()).toBeVisible()
      if (name === 'report') await expect.poll(() => page.locator('.map-image').evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0)
      for (const theme of themes) {
        await page.getByLabel('外观设置', { exact: true }).click()
        await page.locator('.theme-option').nth(themes.indexOf(theme)).click()
        await page.getByLabel('关闭外观设置', { exact: true }).click()
        await inspect(`${name}-${theme}`)
      }
      if (name === 'review') {
        for (const label of ['错题本', '收藏', '掌握概况']) {
          await page.locator('.review-tabs').getByText(label, { exact: true }).click()
          await expect(page.getByText('正在读取学习记录', { exact: true })).toHaveCount(0)
          await inspect(`review-${label}`)
        }
        await page.locator('.review-tabs').getByText('错题本', { exact: true }).click()
        await page.getByText('新建错题本', { exact: true }).click()
        await inspect('notebook-dialog')
        await page.getByLabel('关闭错题本对话框').click()
      }
      if (name === 'path') {
        for (const label of ['前置关系', '历史计划']) {
          await page.locator('.map-tabs').getByText(label, { exact: true }).click()
          await inspect(`path-${label}`)
        }
      }
      if (name === 'tasks') {
        await page.getByText('执行记录', { exact: true }).first().click()
        await inspect('task-trace')
      }
      if (name === 'companion') {
        await page.locator('.room-character-tabs taro-button-core').nth(1).click()
        await expect(page.locator('.room-name')).toHaveText('秋庭澄')
        await inspect('companion-orange')
        for (const label of ['记忆 0', '故事 1/4']) {
          await page.locator('.room-tabs').getByText(label, { exact: true }).click()
          await inspect(`companion-${label.replace('/', '-')}`)
        }
      }
      await page.getByLabel('外观设置', { exact: true }).click()
      await inspect(`${name}-appearance`)
      await page.getByLabel('关闭外观设置', { exact: true }).click()
    }
    expect(errors).toEqual([])
  })
}
