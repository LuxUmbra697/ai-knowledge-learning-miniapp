import test from 'node:test'
import assert from 'node:assert/strict'
import { isPublicPage, safeReturnPath, pageReturnPath } from '../src/services/accessPolicy'
test('home and privacy are public, personal pages remain protected', () => {
  assert.equal(isPublicPage('/pages/index/index'), true)
  assert.equal(isPublicPage('/pages/privacy/index'), true)
  assert.equal(isPublicPage('/pages/profile/index'), false)
  assert.equal(isPublicPage('/learning/assistant/index'), false)
})
test('login return paths cannot become external redirects or carry credentials', () => {
  assert.equal(safeReturnPath('/pages/quiz/index?quizId=quiz_abc'), '/pages/quiz/index?quizId=quiz_abc')
  for (const path of ['https://evil.test', '//evil.test', '/pages/login/index', '/pages/index/index?token=secret', '/pages/quiz/index?quizId=../../other', null]) {
    assert.equal(safeReturnPath(path), '/pages/index/index')
  }
})

test('native and H5 page route conventions both preserve permitted deep-link parameters', () => {
  for (const route of ['learning/document/index', '/learning/document/index', '/ai-learn/learning/document/index']) {
    assert.equal(pageReturnPath(route, { docId: 'guest_document_123', token: 'excluded' }), '/learning/document/index?docId=guest_document_123')
  }
  assert.equal(pageReturnPath('//external.test', {}), '/pages/index/index')
})
