import test from 'node:test'
import assert from 'node:assert/strict'
import { restorableQuiz, quizTaskResult } from '../src/services/quizSession'

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
