import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { writeFile } from 'node:fs/promises'

test('tutor sessions cancel, resume a lost admission and preserve one guiding question with owned citations', async ({ page, request }) => {
  test.setTimeout(70000)
  const account = await request.post('api/v1/user/account/register', { data: { username: `e2e_tutor_${Date.now()}`, password: 'Local-E2E-Only-1976', nickname: '逐步辅导验收' } })
  expect(account.status()).toBe(200)
  const identity = (await account.json()).data, headers = { Authorization: `Bearer ${identity.token}` }
  const python = process.env.E2E_PYTHON || path.resolve('../backend/venv/Scripts/python.exe')
  const seed = (args: string[]) => execFileSync(python, [path.resolve('../scripts/seed_tutor_e2e.py'), '--user-id', String(identity.user.id), ...args], { encoding: 'utf8', windowsHide: true })
  const jsonSeed = (args: string[]) => JSON.parse(seed(args).split(/\r?\n/).find(line => line.startsWith('{'))!)
  const fixture = jsonSeed(['--prepare']), tasks: string[] = [], errors: string[] = []
  let sessionId = '', lost = false
  page.on('pageerror', error => errors.push(error.message))
  try {
    await page.goto('pages/login/index')
    await page.evaluate(user => {
      localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
      localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
    }, identity)
    await page.route('**/tutor/sessions/*/turns', async route => {
      const id = route.request().url().split('/').at(-2)!, body = route.request().postDataJSON()
      sessionId = id
      const held = jsonSeed(['--session-id', id, '--version', String(body.version), '--message', body.message])
      tasks.push(held.taskId)
      const response = await route.fetch()
      expect(response.status()).toBe(200)
      expect((await response.json()).data.task_id).toBe(held.taskId)
      if (lost) await route.abort('timedout')
      else await route.fulfill({ response })
    })
    await page.goto(`learning/tutor/index?docId=${fixture.docId}`)
    await page.locator('textarea').fill('如何检验我是否真正理解了一段知识？')
    await page.getByText('开始辅导', { exact: true }).click()
    await expect(page.getByText('取消本轮', { exact: true })).toBeVisible()
    const positions = await page.getByText('取消本轮', { exact: true }).evaluate(async element => {
      const tops: number[] = []
      for (let sample = 0; sample < 20; sample++) { tops.push(element.getBoundingClientRect().top); await new Promise(resolve => setTimeout(resolve, 30)) }
      return tops
    })
    expect(Math.max(...positions) - Math.min(...positions)).toBeLessThanOrEqual(1)
    await page.getByText('取消本轮', { exact: true }).click()
    await page.locator('.taro-model__confirm').click()
    await expect(page.locator('.tutor-turn')).toHaveCount(0)
    await expect(page.locator('.tutor-composer textarea')).toBeEnabled()
    expect((await (await request.get(`api/v1/learning/tasks/${tasks[0]}`, { headers })).json()).data.status).toBe('cancelled')
    lost = true
    await page.locator('.tutor-composer textarea').fill('我只记得一些关键词，还不能组织成解释。')
    await page.getByText('继续这一轮', { exact: true }).click()
    await expect(page.getByText('网络暂不可用，请检查连接后重试', { exact: true })).toBeVisible()
    const before = await page.evaluate(key => JSON.parse(localStorage.getItem(key)!).data, `ai-learn:v1:tutor:${identity.user.id}`)
    expect(before.sessionId).toBe(sessionId)
    expect(before.turnKey).toBeTruthy()
    expect(before.taskId).toBeUndefined()
    await page.reload()
    await expect(page.getByText('取消本轮', { exact: true })).toBeVisible()
    seed(['--release', tasks[1]])
    await expect(page.locator('.tutor-turn')).toHaveCount(1, { timeout: 15000 })
    await expect(page.locator('.tutor-question')).toHaveText('你能用自己的话解释一个概念吗？')
    await page.getByText('建议练习 · 2 题', { exact: true }).click()
    await expect(page.getByText('创建 2 道“主动回忆”练习？这会调用付费模型。', { exact: true })).toBeVisible()
    await page.locator('.taro-model__cancel').click()
    await page.locator('.tutor-citation .text-button').click()
    await expect(page.getByText('主动回忆可以暴露遗漏。学习时先用自己的话解释概念，再对照原文检查。合成验收材料，不代表学习效果实验。', { exact: true })).toBeVisible()
    await page.goto(`learning/tutor/index?sessionId=${sessionId}`)
    await expect(page.locator('.tutor-turn')).toHaveCount(1)
    lost = false
    await page.locator('.tutor-composer textarea').fill('我先试着说出概念，再找原文检查遗漏。')
    await page.getByText('继续这一轮', { exact: true }).click()
    await expect(page.getByText('取消本轮', { exact: true })).toBeVisible()
    seed(['--release', tasks[2]])
    await expect(page.locator('.tutor-turn')).toHaveCount(2, { timeout: 15000 })
    const result = (await (await request.get(`api/v1/learning/tutor/sessions/${sessionId}`, { headers })).json()).data
    expect(result.version).toBe(2)
    expect(result.turns[1].response.memory_turns).toBe(1)
    for (const id of tasks) expect((await (await request.get(`api/v1/learning/tasks/${id}`, { headers })).json()).data.trace.model_calls).toBe(0)
    for (const width of [320, 390, 1440]) {
      await page.setViewportSize({ width, height: 960 })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    }
    await page.setViewportSize({ width: 390, height: 1000 })
    await page.screenshot({ path: '../docs/screenshots/h5/44-socratic-tutor.png', fullPage: true })
    expect(errors).toEqual([])
    await writeFile('../docs/evidence/tutor-ui.json', JSON.stringify({ recorded_at: new Date().toISOString(),
      environment: 'Chromium + actual API, MySQL and worker', data_source: 'Explicit synthetic held checkpoints', provider_calls: 0,
      checks: ['create_session', 'cancel_first_turn', 'lost_post_response', 'refresh_recovery', 'exactly_one_guiding_question', 'owned_source_navigation',
        'two_persisted_turns', 'bounded_memory', 'declined_paid_practice_does_not_execute', 'mobile_and_desktop_bounds', 'no_browser_errors'],
      limitations: ['No native runtime or real student effectiveness claim'],
    }, null, 2) + '\n')
  } finally { for (const id of tasks) await request.post(`api/v1/learning/tasks/${id}/cancel`, { headers }) }
})

test('saved real tutor responses and user-confirmed diagnosis persist without new model calls', async ({ page, request }) => {
  test.skip(process.env.AI_LEARN_TUTOR_REUSE !== '1', 'Requires the bounded paid tutor fixture; this scenario only reuses its results')
  const { readFile } = await import('node:fs/promises')
  const source = JSON.parse(await readFile('../.local/tutor-browser.json', 'utf8'))
  const headers = { Authorization: `Bearer ${source.account.token}` }
  const diagnosis = (await (await request.get(`api/v1/learning/tutor/sessions/${source.diagnosisId}`, { headers })).json()).data
  expect(diagnosis.card_id).toBe(source.cardId)
  expect(diagnosis.turns[0].response.evidence.some(item => item.source_type === 'stored_practice' && item.content.includes('合成联调题'))).toBeTruthy()
  const getCard = async () => (await (await request.get('api/v1/learning/cards?mode=wrong', { headers })).json()).data.items.find(item => item.card_id === source.cardId)
  const before = await getCard()
  expect(before).toBeTruthy()
  const suggestion = diagnosis.turns[0].response.diagnosis
  expect(suggestion).toBe('concept_confusion')
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, source.account)
  await page.goto(`learning/tutor/index?sessionId=${source.sessionId}`)
  await expect(page.locator('.tutor-turn')).toHaveCount(2)
  await expect(page.locator('.companion')).toHaveCount(0)
  await page.getByLabel('展开学习伙伴', { exact: true }).click()
  await expect(page.locator('.companion-reserved')).toBeVisible()
  expect(await page.locator('.companion-reserved').evaluate(partner => {
    const a = partner.getBoundingClientRect()
    return [...document.querySelectorAll('.tutor-turn, .tutor-composer')].every(node => {
      const b = node.getBoundingClientRect()
      return a.bottom <= b.top || a.top >= b.bottom || a.right <= b.left || a.left >= b.right
    })
  })).toBeTruthy()
  await page.getByLabel('收起学习伙伴', { exact: true }).click()
  for (const text of await page.locator('.tutor-question').allTextContents()) expect((text.match(/[？?]/g) || []).length).toBe(1)
  await page.screenshot({ path: '../docs/screenshots/h5/45-live-socratic-tutor.png', fullPage: true })
  await page.goto(`learning/tutor/index?sessionId=${source.diagnosisId}`)
  await expect(page.locator('.tutor-turn')).toHaveCount(1)
  if (before.diagnosis !== suggestion) {
    await page.getByText('确认错因', { exact: true }).click()
    await page.locator('.taro-model__confirm').click()
    await expect(page.getByText('已记录为你确认的错因，原判分和复习计划未改变。', { exact: true })).toBeVisible()
  }
  await page.reload()
  await expect(page.getByText('模型建议 · 概念混淆 · 你已确认此标记', { exact: true })).toBeVisible()
  const after = await getCard()
  expect(after.diagnosis).toBe(suggestion)
  expect(after.version).toBe(before.version)
  expect(after.due_at).toBe(before.due_at)
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: 960 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  }
  await page.setViewportSize({ width: 390, height: 1000 })
  await page.screenshot({ path: '../docs/screenshots/h5/46-live-wrong-answer-tutor.png', fullPage: true })
  expect(errors).toEqual([])
})

test('explicitly confirmed saved tutor proposal creates one bounded real practice job', async ({ page, request }) => {
  test.skip(process.env.AI_LEARN_TUTOR_PRACTICE_LIVE !== '1', 'Explicit paid integration only: up to two embeddings and six text attempts')
  test.setTimeout(240000)
  const { readFile } = await import('node:fs/promises')
  const source = JSON.parse(await readFile('../.local/tutor-browser.json', 'utf8'))
  const publicText = await readFile('../evaluation/fixtures/learning-rate.md', 'utf8')
  const headers = { Authorization: `Bearer ${source.account.token}` }
  let session = (await (await request.get(`api/v1/learning/tutor/sessions/${source.sessionId}`, { headers })).json()).data
  const started = Date.now()
  for (const id of session.doc_ids) {
    const response = await request.get(`api/v1/knowledge/documents/${id}/chunks`, { headers })
    expect(response.status()).toBe(200)
    const chunks = (await response.json()).data
    expect(chunks.items.length).toBeGreaterThan(0)
    expect(chunks.total).toBe(chunks.items.length)
    expect(chunks.items.every(item => item.doc_id === id && publicText.includes(item.content))).toBeTruthy()
  }
  let proposal = session.turns.find(turn => turn.response.practice)
  let proposalTrace: unknown = null
  if (!proposal) {
    const created = await request.post('api/v1/learning/tutor/sessions', {
      headers: { ...headers, 'Idempotency-Key': `practice_source_${source.sessionId}` },
      data: { mode: 'socratic', goal: session.goal, doc_ids: session.doc_ids },
    })
    expect(created.status()).toBe(200)
    session = (await created.json()).data
    const admitted = await request.post(`api/v1/learning/tutor/sessions/${session.session_id}/turns`, {
      headers: { ...headers, 'Idempotency-Key': `practice_hint_${source.sessionId}` },
      data: { version: 0, message: '我能用自己的话说明步长太大会跨过低点并震荡。下一步想练习，请基于材料建议两道学习率练习，不直接给出题目答案。' },
    })
    expect(admitted.status()).toBe(200)
    const id = (await admitted.json()).data.task_id
    await expect.poll(async () => (await (await request.get(`api/v1/learning/tasks/${id}`, { headers })).json()).data.status,
      { timeout: 100000, intervals: [1000] }).toBe('completed')
    const completed = (await (await request.get(`api/v1/learning/tasks/${id}`, { headers })).json()).data
    expect(completed.trace.model_calls).toBeLessThanOrEqual(4)
    proposalTrace = completed.trace
    session = (await (await request.get(`api/v1/learning/tutor/sessions/${session.session_id}`, { headers })).json()).data
    proposal = session.turns.find(turn => turn.response.practice)
  }
  expect(proposal).toBeTruthy()
  let taskId = ''
  await page.goto('pages/login/index')
  await page.evaluate(user => {
    localStorage.setItem('ai-learn:v1:token', JSON.stringify({ data: user.token }))
    localStorage.setItem('ai-learn:v1:user', JSON.stringify({ data: user.user }))
  }, source.account)
  try {
    await page.goto(`learning/tutor/index?sessionId=${session.session_id}`)
    await page.locator('.tutor-turn').nth(proposal.number - 1).locator('.secondary-button').click()
    const endpoint = `api/v1/learning/tutor/sessions/${session.session_id}/turns/${proposal.number}/practice`
    const response = page.waitForResponse(result => result.url().endsWith(`/turns/${proposal.number}/practice`) && result.request().method() === 'POST')
    await page.locator('.taro-model__confirm').click()
    const admitted = await response
    expect(admitted.status()).toBe(200)
    expect(admitted.request().postDataJSON()).toEqual({ version: session.version, confirmed: true })
    taskId = (await admitted.json()).data.task_id
    const again = await request.post(endpoint, { headers, data: { version: session.version, confirmed: true } })
    expect(again.status()).toBe(200)
    expect((await again.json()).data.task_id).toBe(taskId)
    await expect(page.locator('.question-stem')).toBeVisible({ timeout: 90000 })
    const task = (await (await request.get(`api/v1/learning/tasks/${taskId}`, { headers })).json()).data
    expect(task.status).toBe('completed')
    expect(task.trace.model_calls).toBeLessThanOrEqual(4)
    const quiz = (await (await request.get(`api/v1/user/quizzes/${task.result.quiz_id}`, { headers })).json()).data
    expect(quiz.questions).toHaveLength(proposal.response.practice.count)
    expect(quiz.questions.every(question => !('answer' in question) && !('citations' in question))).toBeTruthy()
    await page.screenshot({ path: '../docs/screenshots/h5/47-live-tutor-practice.png', fullPage: true })
    await writeFile('../.local/tutor-practice-browser.json', JSON.stringify({ account: source.account, taskId, quizId: task.result.quiz_id }))
    await writeFile('../docs/evidence/tutor-practice-live.json', JSON.stringify({ recorded_at: new Date().toISOString(),
      status: 'passed', data_source: 'Verified public learning-rate material and saved real tutor proposal', elapsed_ms: Date.now() - started,
      max_external_calls: 8, proposal_trace: proposalTrace, trace: task.trace, currency_cost: null,
      checks: ['explicit_browser_confirmation', 'canonical_server_proposal', 'same_key_single_task', 'owned_source_scope', 'real_generation', 'proposed_question_count', 'answer_hiding'],
      limitations: ['Question correctness not independently labelled', 'No native runtime verification'],
    }, null, 2) + '\n')
  } finally { if (taskId) await request.post(`api/v1/learning/tasks/${taskId}/cancel`, { headers }) }
})
