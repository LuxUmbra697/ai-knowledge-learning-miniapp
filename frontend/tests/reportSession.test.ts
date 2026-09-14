import { test } from 'node:test'
import assert from 'node:assert/strict'
import { restorableReport, reportTaskMatches } from '../src/services/reportSession'

test('report history restores without storage, and a pending retry supersedes an older link', () => {
  const old = `job_${'a'.repeat(32)}`, latest = `job_${'b'.repeat(32)}`
  assert.equal(restorableReport(old, null)?.taskId, old)
  assert.equal(restorableReport(old, { key: 'new-request', taskId: latest })?.taskId, latest)
  assert.deepEqual(restorableReport(undefined, { key: 'ambiguous-request' }), { key: 'ambiguous-request' })
  assert.equal(restorableReport(undefined, { key: 'bad', taskId: {} }), null)
  assert.equal(restorableReport('../invalid', null), null)
})

test('a report view rejects another quiz or another task kind', () => {
  assert.equal(reportTaskMatches({ kind: 'report', resource_id: 'quiz_a' }, 'quiz_a'), true)
  assert.equal(reportTaskMatches({ kind: 'report', resource_id: 'quiz_b' }, 'quiz_a'), false)
  assert.equal(reportTaskMatches({ kind: 'answer', resource_id: 'quiz_a' }, 'quiz_a'), false)
})
