import { readFile, stat } from 'node:fs/promises'
import assert from 'node:assert/strict'

const html = await readFile('dist/h5/index.html', 'utf8')
assert.match(html, /id="app"/)
assert.match(html, /src="\/ai-learn\/js\//)
assert.doesNotMatch(html, /example\.com|localhost/)
if (process.argv.includes('--both')) {
  const config = JSON.parse(await readFile('dist/weapp/app.json', 'utf8'))
  assert.ok(config.pages.includes('pages/login/index'))
  await stat('dist/weapp/app.js')
}
console.log('Build entry points and base path verified')
