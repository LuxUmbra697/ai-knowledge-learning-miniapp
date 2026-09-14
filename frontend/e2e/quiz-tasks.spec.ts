import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { writeFile } from 'node:fs/promises'

test('private practice tasks cancel, restore and publish no answers before submission', async ({ page, request }) => {
  const register = await request.post('api/v1/user/account/register', { data: { username: `e2e_quiztasks_${Date.now()}`, password: 'Local-E2E-Only-1976', nickname: '练习验收同学' } })
  expect(register.status()).toBe(200)
  const identity = (await register.json()).data
  const headers = { Authorization: `Bearer ${identity.token}` }
  const python = process.env.E2E_PYTHON || path.resolve('../backend/venv/Scripts/python.exe')
  const seed = (args: string[]) => execFileSync(python, [path.resolve('../scripts/seed_e2e.py'), '--user-id', String(identity.user.id), ...args], { encoding: 'utf8', windowsHide: true })
  const seeded: string[] = []
  const fixture = () => {
    const item = JSON.parse(seed(['--quiz-checkpoint']).split(/\r?\n/).find(line => line.startsWith('{'))!)
    seeded.push(item.taskId)
    return item
  }
  const get = async (url: string) => {
    const response = await request.get(`api/v1/${url}`, { headers })
    expect(response.status()).toBe(200)
    return (await response.json()).data
  }
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  try {
    await page.goto('pages/login/index')
    await page.evaluate(user => {
      localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
      localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
    }, identity)
    const cancelled = fixture()
    await page.goto(`pages/quiz/index?taskId=${cancelled.taskId}`)
    await expect(page.getByText('取消练习', { exact: true })).toBeVisible()
    await page.getByText('取消练习', { exact: true }).click()
    await page.getByText('确定', { exact: true }).click()
    await expect(page.getByText('练习任务已取消，未发布新题目', { exact: true })).toBeVisible()
    expect((await get(`learning/tasks/${cancelled.taskId}`)).status).toBe('cancelled')
    expect((await request.get(`api/v1/user/quizzes/${cancelled.quizId}`, { headers })).status()).toBe(404)

    const recovered = fixture()
    for (const corrupt of [{ user_id: identity.user.id + 1 }, { is_correct: true }, { doc_id: '' }, { user_input: '   ' }]) {
      const response = await request.post('api/v1/quiz/generate/async', { headers,
        data: { user_input: recovered.query, question_count: 3, doc_id: recovered.docId, ...corrupt } })
      expect(response.status()).toBe(422)
    }
    const duplicate = await request.post('api/v1/quiz/generate/async', { headers: { ...headers, 'Idempotency-Key': 'e2e-another-device' }, data: { user_input: recovered.query, question_count: 3, doc_id: recovered.docId } })
    expect(duplicate.status()).toBe(200)
    expect((await duplicate.json()).data.task_id).toBe(recovered.taskId)
    await page.goto(`pages/quiz/index?taskId=${recovered.taskId}`)
    await expect(page.getByText('取消练习', { exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByText('取消练习', { exact: true })).toBeVisible()
    await page.screenshot({ path: '../docs/screenshots/h5/17-practice-task.png', fullPage: true })
    await page.goto('learning/tasks/index')
    await page.locator('.task-entry').filter({ has: page.getByText('取消任务', { exact: true }) }).getByText('查看练习', { exact: true }).click()
    await expect(page.getByText('取消练习', { exact: true })).toBeVisible()
    seed(['--release-quiz', recovered.taskId])
    await expect(page.locator('.question-stem')).toBeVisible({ timeout: 15000 })
    const task = await get(`learning/tasks/${recovered.taskId}`)
    expect(task.status).toBe('completed')
    expect(task.trace.model_calls).toBe(0)
    expect(Object.keys(task.result).sort()).toEqual(['quiz_id', 'title'])
    const replay = await request.post('api/v1/quiz/generate/async', { headers: { ...headers, 'Idempotency-Key': 'e2e-another-device' }, data: { user_input: recovered.query, question_count: 3, doc_id: recovered.docId } })
    expect(replay.status()).toBe(200)
    expect((await replay.json()).data.task_id).toBe(recovered.taskId)
    const compatibility = await get(`quiz/task/${recovered.taskId}`)
    expect(compatibility.result.questions.every(q => !('answer' in q) && !('explanation' in q))).toBe(true)
    const detail = await get(`user/quizzes/${recovered.quizId}`)
    expect(detail.questions.every(q => !('answer' in q) && !('explanation' in q))).toBe(true)
    await page.locator('.answer-option').first().click()
    await page.getByText('确认答案', { exact: true }).click()
    await expect(page.getByText('回答正确', { exact: true })).toBeVisible()
    const submitted = await get(`user/quizzes/${recovered.quizId}`)
    expect(submitted.answer_records).toHaveLength(1)
    expect(submitted.questions[0].answer).toEqual(['A'])
    expect(submitted.questions.slice(1).every(q => !('answer' in q))).toBe(true)
    await page.screenshot({ path: '../docs/screenshots/h5/18-recovered-practice.png', fullPage: true })
    await page.reload()
    await expect(page.getByText('多选题', { exact: true })).toBeVisible()
    await page.getByText('上一题', { exact: true }).click()
    await expect(page.getByText('回答正确', { exact: true })).toBeVisible()
    await page.goto('learning/tasks/index')
    await page.locator('.task-entry').filter({ has: page.getByText('已完成', { exact: true }) }).getByText('查看练习', { exact: true }).click()
    await expect(page.getByText('多选题', { exact: true })).toBeVisible()
    expect((await get('user/profile')).total_xp).toBe(0)
    await page.evaluate(({ userId, docId }) => localStorage.setItem(`ai-learn:v1:practice:${userId}:${docId}`,
      JSON.stringify({ data: { key: 'e2e-stale-reference', taskId: 'job_' + '0'.repeat(32) } })), { userId: identity.user.id, docId: recovered.docId })
    await page.goto('pages/knowledge/index')
    const document = page.locator('.document-row').filter({ has: page.getByText('合成练习恢复验收.md', { exact: true }) })
    const missingTask = '**/learning/tasks/job_' + '0'.repeat(32)
    await page.route(missingTask, route => route.abort('timedout'))
    await document.getByText('知识练习', { exact: true }).click()
    await expect(page.getByText('网络暂不可用，请检查连接后重试', { exact: true })).toBeVisible()
    expect(await page.evaluate(({ userId, docId }) => localStorage.getItem(`ai-learn:v1:practice:${userId}:${docId}`),
      { userId: identity.user.id, docId: recovered.docId })).not.toBeNull()
    await page.unroute(missingTask)
    await document.getByText('知识练习', { exact: true }).click()
    await expect(page.getByText('任务不存在', { exact: true })).toBeVisible()
    expect(await page.evaluate(({ userId, docId }) => localStorage.getItem(`ai-learn:v1:practice:${userId}:${docId}`),
      { userId: identity.user.id, docId: recovered.docId })).toBeNull()
    expect(errors).toEqual([])
    await writeFile('../docs/evidence/m3-quiz-task-ui.json', JSON.stringify({
      recorded_at: new Date().toISOString(), environment: 'Chromium + local API + isolated MySQL + actual worker',
      data_source: 'Explicit synthetic checkpoint, not real model output', provider_calls: 0,
      checks: ['cancel_does_not_publish', 'forged_and_empty_inputs_rejected', 'different_key_coalesces_active_job', 'pending_refresh_and_history_restore',
        'worker_validates_checkpoint_without_model', 'coalesced_key_replays_after_completion', 'generic_task_result_has_no_questions', 'answers_hidden_until_submission',
        'server_attempt_persists_on_refresh', 'history_opens_completed_practice', 'network_failure_retains_request_key', 'invalid_local_reference_cleared_after_404', 'no_browser_errors'],
      limitations: ['Not native WeChat verification', 'No model quality or learning efficacy claim'],
    }, null, 2) + '\n')
  } finally {
    for (const taskId of seeded) await request.post(`api/v1/learning/tasks/${taskId}/cancel`, { headers })
  }
})
