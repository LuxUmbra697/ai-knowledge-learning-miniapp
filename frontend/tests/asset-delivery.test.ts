import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { assetUrl, ASSET_BASE_URL, companionFrames } from '../src/services/assets'

const root = fileURLToPath(new URL('../', import.meta.url))
function files(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const target = path.join(directory, entry.name)
    return entry.isDirectory() ? files(target) : [target]
  })
}

test('runtime source never imports packaged artwork or icons', () => {
  const source = files(path.join(root, 'src')).filter(name => /\.(?:tsx?|scss)$/.test(name))
  for (const name of source) assert.doesNotMatch(readFileSync(name, 'utf8'), /(?:require\(|from\s+|url\()\s*['"][^'"]*\/assets\//, path.relative(root, name))
})

test('WeChat upload requests code minification and component lazy loading', () => {
  const config = JSON.parse(readFileSync(path.join(root, 'project.config.json'), 'utf8'))
  assert.equal(config.setting.minified, true)
  assert.match(readFileSync(path.join(root, 'src/app.config.ts'), 'utf8'), /lazyCodeLoading:\s*['"]requiredComponents['"]/)
})

test('public asset paths preserve the OSS directory and reject arbitrary URLs', () => {
  assert.equal(assetUrl('academy-gate.jpg'), ASSET_BASE_URL + 'academy-gate.jpg')
  assert.equal(assetUrl('icons/arrow-up-right.png'), ASSET_BASE_URL + 'icons/arrow-up-right.png')
  for (const value of ['../secret.png', '/x.png', 'https://other/x.png', 'icons\\x.png', 'x.png?key=secret', 'x.png#fragment', '%2e%2e/x.png', 'x.svg']) {
    assert.throws(() => assetUrl(value), /Invalid public asset path/)
  }
  assert.equal(new Set(Object.values(companionFrames).flat()).size, 6)
  for (const url of Object.values(companionFrames).flat()) assert.ok(url.startsWith(ASSET_BASE_URL))
})
