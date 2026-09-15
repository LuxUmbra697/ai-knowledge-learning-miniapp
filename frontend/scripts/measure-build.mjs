import { mkdir, readdir, readFile, writeFile } from 'node:fs/promises'
import { gzipSync } from 'node:zlib'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const distribution = fileURLToPath(new URL('../dist/', import.meta.url))

async function files(directory) {
  const result = []
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const filename = path.join(directory, entry.name)
    if (entry.isDirectory()) result.push(...await files(filename))
    else result.push(filename)
  }
  return result
}
const result = { measured_at: new Date().toISOString(), node: process.version, taro: '4.1.11', budgets: { h5_entry_gzip_bytes: 180000, weapp_main_bytes: 2 * 1024 * 1024 }, platforms: {} }
for (const platform of ['h5', 'weapp']) {
  const all = await files(path.join(distribution, platform))
  let bytes = 0
  for (const filename of all) bytes += (await readFile(filename)).byteLength
  result.platforms[platform] = { files: all.length, bytes }
  if (platform === 'weapp') {
    const config = JSON.parse(await readFile(path.join(distribution, 'weapp/app.json'), 'utf8'))
    const roots = (config.subPackages || config.subpackages || []).map(item => item.root.replace(/\/$/, '') + '/')
    let main = 0
    const packages = Object.fromEntries(roots.map(root => [root, 0]))
    for (const filename of all) {
      const relative = path.relative(path.join(distribution, 'weapp'), filename).replaceAll('\\', '/')
      const root = roots.find(prefix => relative.startsWith(prefix))
      const size = (await readFile(filename)).byteLength
      if (root) packages[root] += size
      else main += size
    }
    result.platforms[platform].main_bytes = main
    result.platforms[platform].subpackages = packages
  }
}
const html = await readFile(path.join(distribution, 'h5/index.html'), 'utf8')
const entries = [...html.matchAll(/(?:src|href)="\/ai-learn\/((?:js|css)\/[^"?#]+)"/g)].map(match => match[1])
let entryGzip = 0
for (const file of entries) entryGzip += gzipSync(await readFile(path.join(distribution, 'h5', file))).length
result.platforms.h5.entry_gzip_bytes = entryGzip
result.budgets_passed = entryGzip <= result.budgets.h5_entry_gzip_bytes && result.platforms.weapp.main_bytes <= result.budgets.weapp_main_bytes
const output = process.argv.includes('--output') ? process.argv[process.argv.indexOf('--output') + 1] : fileURLToPath(new URL('../../docs/evidence/build-size.json', import.meta.url))
await mkdir(path.dirname(output), { recursive: true })
await writeFile(output, JSON.stringify(result, null, 2) + '\n')
console.log(JSON.stringify(result, null, 2))
if (!result.budgets_passed) process.exitCode = 1
