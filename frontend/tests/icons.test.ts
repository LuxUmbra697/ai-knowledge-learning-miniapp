import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import path from 'node:path'
import ts from 'typescript'

test('every literal shared Icon action has a registered asset instead of silently becoming a book', () => {
  const parse = (file: string) => ts.createSourceFile(file, readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const registry = parse(path.resolve('src/components/Icon.tsx')), known = new Set<string>(), missing: string[] = []
  const visitRegistry = (node: ts.Node) => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.name.text === 'icons' && node.initializer && ts.isObjectLiteralExpression(node.initializer)) {
      for (const prop of node.initializer.properties) if (ts.isPropertyAssignment(prop) && ts.isIdentifier(prop.name)) known.add(prop.name.text)
    }
    ts.forEachChild(node, visitRegistry)
  }
  visitRegistry(registry)
  for (const name of readdirSync('src', { recursive: true }) as string[]) {
    if (!name.endsWith('.tsx')) continue
    const tree = parse(path.join('src', name))
    const visit = (node: ts.Node) => {
      if ((ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) && node.tagName.getText(tree) === 'Icon') {
        for (const attr of node.attributes.properties) if (ts.isJsxAttribute(attr) && attr.name.getText(tree) === 'name' && attr.initializer && ts.isStringLiteral(attr.initializer) && !known.has(attr.initializer.text)) missing.push(`${name}: ${attr.initializer.text}`)
      }
      ts.forEachChild(node, visit)
    }
    visit(tree)
  }
  assert.deepEqual(missing, [])
})
