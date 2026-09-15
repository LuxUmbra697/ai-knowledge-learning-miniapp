import { readFile, stat } from 'node:fs/promises'
import assert from 'node:assert/strict'

const html = await readFile(new URL('../dist/h5/index.html', import.meta.url), 'utf8')
assert.match(html, /id="app"/)
assert.match(html, /src="\/ai-learn\/js\//)
assert.doesNotMatch(html, /example\.com|localhost/)
if (process.argv.includes('--both')) {
  const config = JSON.parse(await readFile(new URL('../dist/weapp/app.json', import.meta.url), 'utf8'))
  assert.ok(config.pages.includes('pages/login/index'))
  await stat(new URL('../dist/weapp/app.js', import.meta.url))
}
console.log('Build entry points and base path verified')
