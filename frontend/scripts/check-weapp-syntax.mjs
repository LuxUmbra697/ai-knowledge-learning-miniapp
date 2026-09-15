import { readdir, readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { parse } from 'acorn'

const root = fileURLToPath(new URL('../dist/weapp/', import.meta.url))
let checked = 0
async function walk(directory) {
  for (const item of await readdir(directory, { withFileTypes: true })) {
    const filename = path.join(directory, item.name)
    if (item.isDirectory()) await walk(filename)
    else if (filename.endsWith('.js')) {
      try { parse(await readFile(filename, 'utf8'), { ecmaVersion: 2019, sourceType: 'script' }) }
      catch (error) { throw new Error(`WeChat upload syntax gate: ${path.relative(root, filename)}:${error.loc.line}:${error.loc.column}`) }
      checked++
    }
  }
}
await walk(root)
if (!checked) throw new Error('Build weapp before syntax verification')
console.log(JSON.stringify({ weapp_javascript_files: checked, syntax: 'ECMAScript 2019', passed: true }))
