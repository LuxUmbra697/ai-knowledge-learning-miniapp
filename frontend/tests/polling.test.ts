import { test } from 'node:test'
import assert from 'node:assert/strict'
import { pollUntil, PollControl } from '../src/services/polling'

test('slow requests never overlap and polling begins immediately', async () => {
  let active = 0, peak = 0, count = 0
  const result = await pollUntil(async () => {
    active++; peak = Math.max(peak, active)
    await new Promise(resolve => setTimeout(resolve, 15))
    active--; return ++count
  }, value => value === 3, { intervalMs: 1, maxAttempts: 4 })
  assert.equal(result, 3); assert.equal(peak, 1); assert.equal(count, 3)
})

test('cancellation aborts pending transport and prevents another request', async () => {
  const control = new PollControl()
  let aborted = false, count = 0
  const result = pollUntil(async () => {
    count++
    control.onCancel(() => { aborted = true })
    await new Promise(resolve => setTimeout(resolve, 15))
    return false
  }, Boolean, { control, intervalMs: 1 })
  setTimeout(() => control.cancel(), 2)
  await assert.rejects(result, /cancelled/)
  assert.equal(aborted, true); assert.equal(count, 1)
})

test('attempt limit and permanent request errors terminate deterministically', async () => {
  let count = 0
  await assert.rejects(pollUntil(async () => ++count, () => false, { intervalMs: 0, maxAttempts: 3 }), /timeout/)
  assert.equal(count, 3)
  await assert.rejects(pollUntil(async () => { throw new Error('401') }, () => false), /401/)
})

test('cancellation inside a progress callback does not access an uninitialized timer', async () => {
  const control = new PollControl()
  await assert.rejects(pollUntil(async () => false, () => { control.cancel(); return false }, { control }), /poll cancelled/)
})
