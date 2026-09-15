import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { readFile, writeFile } from 'node:fs/promises'

test('bounded real report task survives refresh and deduplicates publication', async ({ page, request }) => {
  test.skip(process.env.AI_LEARN_LIVE_REPORT !== '1', 'Explicit opt-in: at most three chat calls for one report, no embeddings or images')
  test.setTimeout(100000)
  const reuse = process.env.AI_LEARN_REPORT_REUSE === '1'
  let identity, quizId: string, taskId: string
  const get = async (url: string) => {
    const response = await request.get(`api/v1/${url}`, { headers: { Authorization: `Bearer ${identity.token}` } })
    expect(response.status()).toBe(200)
    return (await response.json()).data
  }
  if (reuse) {
    ({ identity, quizId, taskId } = JSON.parse(await readFile('../.local/report-browser.json', 'utf8')))
  } else {
    const register = await request.post('api/v1/user/account/register', { data: { username: `e2e_report_live_${Date.now()}`, password: 'Local-E2E-Only-1976', nickname: '复盘验收同学' } })
    expect(register.status()).toBe(200)
    identity = (await register.json()).data
    const python = process.env.E2E_PYTHON || path.resolve('../backend/venv/Scripts/python.exe')
    const output = execFileSync(python, [path.resolve('../scripts/seed_e2e.py'), '--user-id', String(identity.user.id)], { encoding: 'utf8', windowsHide: true })
    quizId = output.split(/\r?\n/).find(line => line.startsWith('quiz_e2e_'))!
    const detail = await get(`user/quizzes/${quizId}`)
    for (const q of detail.questions) {
      const submitted = await request.post(`api/v1/quiz/${quizId}/answer`, { headers: { Authorization: `Bearer ${identity.token}` },
        data: { question_id: q.id, selected_answers: q.type === 'multiple' ? ['A', 'B'] : ['B'] } })
      expect(submitted.status()).toBe(200)
    }
  }
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, identity)
  await page.goto(`pages/report/index?quizId=${quizId}`)
  const started = Date.now()
  if (!reuse) {
    const pending = page.waitForResponse(response => response.url().endsWith('/report/generate/async'))
    await page.getByText('生成学习报告', { exact: true }).click()
    const response = await pending
    expect(response.status()).toBe(200)
    taskId = (await response.json()).data.task_id
    await writeFile('../.local/report-browser.json', JSON.stringify({ identity, quizId, taskId }) + '\n')
    const duplicate = await request.post('api/v1/report/generate/async', { headers: { Authorization: `Bearer ${identity.token}`,
      'Idempotency-Key': `second_device_${Date.now()}` }, data: { quiz_id: quizId } })
    expect((await duplicate.json()).data.task_id).toBe(taskId)
    await page.reload()
  }
  await expect(page.getByText('本次总结', { exact: true })).toBeVisible({ timeout: 75000 })
  await expect(page.getByText('67%', { exact: true })).toBeVisible()
  const elapsed = Date.now() - started
  const task = await get(`learning/tasks/${taskId!}`)
  expect(task.status).toBe('completed')
  expect(task.trace.model_calls).toBeGreaterThanOrEqual(1)
  expect(task.trace.model_calls).toBeLessThanOrEqual(3)
  expect(task.trace.tokens).toBeGreaterThan(0)
  expect(task.result.accuracy).toBe(67)
  expect(task.trace.nodes.map(node => node.stage)).toContain('report_validated')
  const profile = await get('user/profile')
  expect(profile.total_xp).toBe(14)
  const repeat = await request.post('api/v1/report/generate', { headers: { Authorization: `Bearer ${identity.token}` }, data: { quiz_id: quizId } })
  expect((await repeat.json()).data).toEqual(task.result)
  expect((await get('user/profile')).total_xp).toBe(14)
  await page.screenshot({ path: '../docs/screenshots/h5/15-durable-report.png', fullPage: true })
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.screenshot({ path: '../docs/screenshots/h5/16-report-desktop.png', fullPage: true })
  expect(await page.locator('body').evaluate(node => node.scrollWidth <= window.innerWidth)).toBeTruthy()
  expect(errors).toEqual([])
  await writeFile(`../docs/evidence/m3-report-${reuse ? 'resume' : 'live'}.json`, JSON.stringify({ recorded_at: new Date().toISOString(),
    source: 'Synthetic exercise with actual model-generated report', run_mode: reuse ? 'saved report, no new model calls' : 'new bounded report task',
    observed_ui_ms: elapsed, task_trace: task.trace, accuracy: task.result.accuracy, total_xp: profile.total_xp,
    checks: [...(reuse ? [] : ['duplicate_device_same_task', 'refresh_pending_report']), 'actual_provider_output', 'server_accuracy', 'atomic_report_xp',
      'compatibility_endpoint_reuses_result', '390_and_1440_width', 'no_browser_errors'],
    limitations: ['No human rating of diagnosis', 'No native WeChat execution', 'Currency billing not queried'],
  }, null, 2) + '\n')
})
