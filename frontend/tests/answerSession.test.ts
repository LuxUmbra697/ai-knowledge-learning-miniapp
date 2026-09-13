import { test } from 'node:test'
import assert from 'node:assert/strict'
import { restorableAnswer } from '../src/services/answerSession'

test('refresh from a document-specific assistant restores its task, unrelated documents do not', () => {
  const saved = { taskId: 'job_a', docIds: ['doc_a'] }
  assert.equal(restorableAnswer({ docId: 'doc_a' }, saved), 'job_a')
  assert.equal(restorableAnswer({ docId: 'doc_b' }, saved), '')
  assert.equal(restorableAnswer({}, saved), 'job_a')
  assert.equal(restorableAnswer({ taskId: 'job_b' }, saved), 'job_b')
  assert.equal(restorableAnswer({}, null), '')
})
