import test from 'node:test'
import assert from 'node:assert/strict'
import { restorableQuiz, quizTaskResult, restorableTopic } from '../src/services/quizSession'
import { defaultCounts } from '../src/services/quizBlueprint'

test('private practice retries retain a validated request key and task identity', () => {
  const pending = { key: 'quiz_test_key', taskId: 'job_' + 'a'.repeat(32) }
  assert.deepEqual(restorableQuiz(pending), pending)
  assert.deepEqual(restorableQuiz({ key: pending.key }), { key: pending.key, taskId: undefined })
  for (const value of [null, { key: 'x' }, { ...pending, taskId: '../wrong' }, { ...pending, key: {} }]) assert.equal(restorableQuiz(value), null)
})

test('practice history only opens a completed quiz task reference', () => {
  assert.equal(quizTaskResult({ kind: 'quiz', status: 'running' }), null)
  assert.equal(quizTaskResult({ kind: 'quiz', status: 'completed', result: { quiz_id: 'quiz_' + 'b'.repeat(32) } }), 'quiz_' + 'b'.repeat(32))
  assert.throws(() => quizTaskResult({ kind: 'report', status: 'completed', result: { quiz_id: 'quiz_' + 'b'.repeat(32) } }))
  assert.throws(() => quizTaskResult({ kind: 'quiz', status: 'completed', result: { quiz_id: '../wrong' } }))
})

test('topic recovery preserves the exact request and validates untrusted storage', () => {
  const value = { key: 'topic_request_1234', taskId: `job_${'a'.repeat(32)}`, input: '中文主题', counts: defaultCounts(), web: true }
  assert.deepEqual(restorableTopic(value), value)
  for (const invalid of [{ ...value, input: '' }, { ...value, counts: {} }, { ...value, web: 'yes' }, { ...value, taskId: 'other-user-path' }]) assert.equal(restorableTopic(invalid), null)
})
