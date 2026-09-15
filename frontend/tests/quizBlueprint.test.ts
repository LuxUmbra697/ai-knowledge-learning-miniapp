import { test } from 'node:test'
import assert from 'node:assert/strict'
import { defaultCounts, countQuestions, validCounts } from '../src/services/quizBlueprint'

test('total presets stay bounded and exact, with legacy three-type distribution', () => {
  for (let total = 1; total <= 20; total++) {
    const value = defaultCounts(total)
    assert.equal(countQuestions(value), total)
    assert.equal(validCounts(value), true)
    assert.equal(value.fill + value.written, 0)
    if (total >= 3) assert.ok(value.single && value.multiple && value.judge)
  }
})

test('custom text-only quotas work while empty and over-budget totals are rejected', () => {
  assert.equal(validCounts({ single: 0, multiple: 0, judge: 0, fill: 2, written: 3 }), true)
  assert.equal(validCounts(defaultCounts(0)), false)
  assert.equal(validCounts({ ...defaultCounts(20), written: 1 }), false)
  assert.equal(validCounts({ ...defaultCounts(5), single: 1.5 }), false)
})
