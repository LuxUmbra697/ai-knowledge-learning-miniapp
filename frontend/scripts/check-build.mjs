import { readFile, stat } from 'node:fs/promises'
import assert from 'node:assert/strict'

const html = await readFile(new URL('../dist/h5/index.html', import.meta.url), 'utf8')
assert.match(html, /id="app"/)
assert.match(html, /src="\/ai-learn\/js\//)
assert.doesNotMatch(html, /example\.com|localhost/)
if (process.argv.includes('--both')) {
  const project = JSON.parse(await readFile(new URL('../project.config.json', import.meta.url), 'utf8'))
  assert.equal(project.appid, 'wx7abde39fb8222887', 'This deployment uses the owner-designated WeChat AppID')
  const builtProject = JSON.parse(await readFile(new URL('../dist/weapp/project.config.json', import.meta.url), 'utf8'))
  assert.ok(project.appid === builtProject.appid, 'Built WeChat AppID must match the project configuration')
  assert.ok(!process.env.AI_LEARN_WECHAT_APP_ID || project.appid === process.env.AI_LEARN_WECHAT_APP_ID,
    'WeChat project AppID must match the configured backend identity')
  const config = JSON.parse(await readFile(new URL('../dist/weapp/app.json', import.meta.url), 'utf8'))
  assert.ok(config.pages.includes('pages/login/index'))
  await stat(new URL('../dist/weapp/app.js', import.meta.url))
}
console.log('Build entry points and base path verified')
