import assert from 'node:assert/strict'
import test from 'node:test'
import { checkedMap, diagramView, mermaidSource, type StudyMap } from '../src/services/learningMap'
import { layoutMap } from '../src/services/mapLayout'

const fixture: StudyMap = { version: 'study-map-v1', source_hash: 'a'.repeat(64), mapping_basis: 'generated-question-tags',
  nodes: [{ id: 'root', kind: 'topic', label: '学习' }, { id: 'c0', kind: 'concept', label: '回忆' },
    { id: 'q0', kind: 'question', label: '第1题', state: 'wrong', question_id: 'a' }, { id: 'q1', kind: 'question', label: '第2题', state: 'correct', question_id: 'b' },
    { id: 's0', kind: 'source', label: '原文', doc_id: 'd', chunk_id: 'c', revision: 1 }],
  edges: [{ source: 'root', target: 'c0', relation: 'contains' }, { source: 'c0', target: 'q0', relation: 'assesses' },
    { source: 'c0', target: 'q1', relation: 'assesses' }, { source: 'q0', target: 's0', relation: 'supported_by' }] }

test('wrong maps retain provenance, networks keep shared links and empty sets stay empty', () => {
  assert.deepEqual(diagramView(fixture, 'wrong').nodes.map(n => n.id), ['root', 'c0', 'q0', 's0'])
  assert.equal(diagramView(fixture, 'outline').nodes.length, 4)
  assert.equal(diagramView(fixture, 'network').nodes.length, 5)
  assert.equal(diagramView({ ...fixture, nodes: fixture.nodes.map(n => ({ ...n, state: 'correct' })) }, 'wrong').nodes.length, 0)
})

test('generated Mermaid encodes all label syntax and rejects noncanonical IDs and dangling edges', () => {
  const hostile = { ...fixture, nodes: fixture.nodes.map(n => ({ ...n, label: '<img onerror=alert(1)>"\n%%{init:securityLevel=loose}%%' })) }
  const code = mermaidSource(hostile)
  assert.ok(!code.includes('<img') && !code.includes('%%') && !code.includes('>"\n'))
  assert.ok(code.includes('〈img') && !code.includes('#60;'))
  assert.ok(mermaidSource(fixture).includes('回忆'))
  assert.throws(() => checkedMap({ ...fixture, nodes: [{ ...fixture.nodes[0], id: 'click X evil' }] }))
  assert.throws(() => checkedMap({ ...fixture, edges: [{ source: 'bad', target: 'root', relation: 'contains' }] }))
})

test('native Dagre geometry has stable dimensions, finite routes and nonoverlapping nodes', () => {
  const layout = layoutMap(fixture)
  assert.ok(layout.width > 0 && layout.height > 0)
  for (const [i, node] of layout.nodes.entries()) {
    assert.ok(Number.isFinite(node.x) && Number.isFinite(node.y))
    for (const other of layout.nodes.slice(i + 1)) assert.ok(Math.abs(node.x - other.x) >= 172 || Math.abs(node.y - other.y) >= 64)
  }
  assert.equal(layout.edges.length, fixture.edges.length)
})
