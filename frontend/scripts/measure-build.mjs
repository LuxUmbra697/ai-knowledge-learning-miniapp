import { readdir, readFile, writeFile } from 'node:fs/promises'
import { gzipSync } from 'node:zlib'
import path from 'node:path'

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
  const all = await files(`dist/${platform}`)
  let bytes = 0
  for (const filename of all) bytes += (await readFile(filename)).byteLength
  result.platforms[platform] = { files: all.length, bytes }
}
const html = await readFile('dist/h5/index.html', 'utf8')
const entries = [...html.matchAll(/(?:src|href)="\/ai-learn\/((?:js|css)\/[^"?#]+)"/g)].map(match => match[1])
let entryGzip = 0
for (const file of entries) entryGzip += gzipSync(await readFile(`dist/h5/${file}`)).length
result.platforms.h5.entry_gzip_bytes = entryGzip
result.budgets_passed = entryGzip <= result.budgets.h5_entry_gzip_bytes && result.platforms.weapp.bytes <= result.budgets.weapp_main_bytes
await writeFile('../docs/evidence/m1-build-size.json', JSON.stringify(result, null, 2) + '\n')
console.log(JSON.stringify(result, null, 2))
if (!result.budgets_passed) process.exitCode = 1
