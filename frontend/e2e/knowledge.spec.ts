import { test, expect } from '@playwright/test'

test('real file picker uploads damaged PDF and persists actionable failure', async ({ page, request }) => {
  const response = await request.post('api/v1/user/account/register', { data: { username: `e2e_upload_${Date.now()}`, password: 'Local-E2E-Only-1976', nickname: '资料验收同学' } })
  expect(response.status()).toBe(200)
  const identity = (await response.json()).data
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, identity)
  await page.goto('pages/knowledge/index')
  await expect(page.getByText('书架上还没有学习材料', { exact: true })).toBeVisible()
  const picker = page.waitForEvent('filechooser')
  await page.getByText('添加学习材料', { exact: true }).click()
  await (await picker).setFiles({ name: '损坏文件验收.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-broken') })
  await expect(page.getByText('损坏文件验收.pdf', { exact: true })).toBeVisible()
  await expect(page.getByText('PDF 文件损坏或无法解析，请重新导出文件', { exact: true })).toBeVisible({ timeout: 15000 })
  await page.reload()
  await expect(page.getByText('PDF 文件损坏或无法解析，请重新导出文件', { exact: true })).toBeVisible()
  await page.screenshot({ path: '../docs/screenshots/h5/03-upload-feedback.png', fullPage: true })
  const list = await request.get('api/v1/knowledge/documents', { headers: { Authorization: `Bearer ${identity.token}` } })
  const docs = (await list.json()).data.items
  expect(docs).toHaveLength(1)
  expect(docs[0].status).toBe('failed')
  expect(docs[0].chunk_count).toBe(0)
})
