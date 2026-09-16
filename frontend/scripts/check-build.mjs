import { readFile, stat, readdir } from 'node:fs/promises'
import assert from 'node:assert/strict'

const html = await readFile(new URL('../dist/h5/index.html', import.meta.url), 'utf8')
assert.match(html, /id="app"/)
assert.match(html, /src="\/ai-learn\/js\//)
assert.match(html, /\/ai-learn\/js\/app\.[a-f0-9]{12}\.js/, 'H5 entry must be content-addressed')
assert.match(html, /\/ai-learn\/css\/app\.[a-f0-9]{12}\.css/, 'H5 styles must not reuse stale URLs')
assert.doesNotMatch(html, /example\.com|localhost/)
if (process.argv.includes('--both')) {
  const project = JSON.parse(await readFile(new URL('../project.config.json', import.meta.url), 'utf8'))
  assert.equal(project.appid, 'wx7abde39fb8222887', 'This deployment uses the owner-designated WeChat AppID')
  const builtProject = JSON.parse(await readFile(new URL('../dist/weapp/project.config.json', import.meta.url), 'utf8'))
  assert.ok(project.appid === builtProject.appid, 'Built WeChat AppID must match the project configuration')
  assert.equal(builtProject.setting.minified, true, 'WeChat JS minification must be enabled for upload')
  assert.ok(!process.env.AI_LEARN_WECHAT_APP_ID || project.appid === process.env.AI_LEARN_WECHAT_APP_ID,
    'WeChat project AppID must match the configured backend identity')
  const config = JSON.parse(await readFile(new URL('../dist/weapp/app.json', import.meta.url), 'utf8'))
  assert.ok(config.pages.includes('pages/login/index'))
  assert.equal(config.lazyCodeLoading, 'requiredComponents', 'Component injection must be on demand')
  const root = new URL('../dist/weapp/', import.meta.url)
  async function mediaBytes(directory) {
    let total = 0
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const child = new URL(entry.name + (entry.isDirectory() ? '/' : ''), directory)
      if (entry.isDirectory()) total += await mediaBytes(child)
      else if (/\.(?:png|jpe?g|gif|webp|svg|mp3|mp4|wav|ogg|aac)$/i.test(entry.name)) total += (await stat(child)).size
    }
    return total
  }
  const media = await mediaBytes(root)
  assert.ok(media <= 200 * 1024, `Packaged media exceeds 200 KiB: ${media}`)
  assert.equal(media, 0, 'Public artwork and icons must be served from OSS, not bundled')
  console.log(`WeChat upload gates: minified JS, lazy components, ${media} packaged media bytes`)
  await stat(new URL('../dist/weapp/app.js', import.meta.url))
  await import('./check-weapp-syntax.mjs')
}
console.log('Build entry points and base path verified')
