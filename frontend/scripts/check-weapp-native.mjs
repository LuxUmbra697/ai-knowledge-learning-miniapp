import { readdir, readFile } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import path from 'node:path'

const root = fileURLToPath(new URL('../dist/weapp/', import.meta.url))
const compiler = process.env.WECHAT_WXSS_COMPILER
assert.ok(compiler, 'Set WECHAT_WXSS_COMPILER to the installed official WeChat wcsc executable')
assert.equal(JSON.parse(await readFile(path.join(root, 'project.config.json'), 'utf8')).appid, 'wx7abde39fb8222887')
async function files(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const result = []
  for (const entry of entries) {
    const name = path.join(directory, entry.name)
    if (entry.isDirectory()) result.push(...await files(name))
    else if (entry.isFile() && name.endsWith('.wxss')) result.push(path.relative(root, name).replaceAll('\\', '/'))
  }
  return result
}
const styles = await files(root)
assert.ok(styles.length > 0, 'Build weapp before running native compilation validation')
const result = spawnSync(compiler, ['-lc', ...styles], { cwd: root, encoding: 'utf8', timeout: 60000, maxBuffer: 8 * 1024 * 1024, windowsHide: true })
if (result.status !== 0) {
  console.error((result.stderr || result.error?.message || 'Native compiler failed').slice(0, 4000))
  process.exit(1)
}
console.log(JSON.stringify({ compiler: 'Official WeChat WXSS', files: styles.length, appid: 'wx7abde39fb8222887', compiled: true }))
