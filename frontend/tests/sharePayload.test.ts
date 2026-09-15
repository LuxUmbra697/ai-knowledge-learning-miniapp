import test from 'node:test'
import assert from 'node:assert/strict'
import { publicSharePayload } from '../src/services/sharePayload'

test('WeChat sharing includes only a public entry, never private report or account identifiers', () => {
  assert.deepEqual(publicSharePayload(), { title: '星知学园 · 把好奇变成理解', path: '/pages/index/index' })
  const edited = publicSharePayload()
  edited.path = '/private'
  assert.equal(publicSharePayload().path, '/pages/index/index')
})
