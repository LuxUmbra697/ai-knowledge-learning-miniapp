import { test } from 'node:test'
import assert from 'node:assert/strict'
import { tutorDraft } from '../src/services/tutorSession'

test('tutor restores exact bounded requests without introducing identity or execution commands', () => {
  const value = { config: { goal: 'Learn', mode: 'socratic', doc_ids: ['doc_a'] }, createKey: 'create_fixture',
    sessionId: 'tutor_' + 'a'.repeat(32), version: 0, message: 'My first reply', turnKey: 'turn_fixture', taskId: 'job_' + 'b'.repeat(32) }
  assert.deepEqual(tutorDraft(value), value)
  for (const changed of [{ version: -1 }, { version: 6 }, { taskId: '../other-task' }, { message: 'x'.repeat(1001) },
    { config: { ...value.config, doc_ids: [] } }, { config: { ...value.config, mode: 'diagnosis' } }, { createKey: 'bad!' },
    { config: { ...value.config, user_id: 99 } }, { config: { ...value.config, mode: 'diagnosis', doc_ids: [], card_id: 99 } }]) {
    assert.equal(tutorDraft({ ...value, ...changed }), null)
  }
  assert.ok(tutorDraft({ config: { goal: 'Review', mode: 'diagnosis', doc_ids: [], card_id: 'card_fixture' }, createKey: 'diagnosis_fixture' }))
})
