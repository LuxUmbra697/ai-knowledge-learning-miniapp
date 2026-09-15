import test from 'node:test'
import assert from 'node:assert/strict'
import { compile } from 'sass'
import postcss from 'postcss'
import selectors from 'postcss-selector-parser'

test('shared styles contain no universal selectors rejected by the WeChat compiler', () => {
  const css = postcss.parse(compile('src/app.scss').css)
  const invalid: string[] = []
  css.walkRules(rule => {
    selectors(root => root.walkUniversals(() => { invalid.push(rule.selector) })).processSync(rule.selector)
  })
  assert.deepEqual(invalid, [])
})
