export interface MapNode {
  id: string; kind: 'topic' | 'concept' | 'question' | 'source'; label: string; detail?: string
  state?: 'neutral' | 'correct' | 'wrong'; question_id?: string | null
  doc_id?: string | null; chunk_id?: string | null; revision?: number | null
}
export interface MapEdge { source: string; target: string; relation: 'contains' | 'assesses' | 'supported_by' | 'precedes' }
export interface StudyMap { version: 'study-map-v1'; source_hash: string; mapping_basis: string; nodes: MapNode[]; edges: MapEdge[] }
export type MapMode = 'outline' | 'network' | 'wrong'
export const edgeLabels = { contains: '包含', assesses: '考查', supported_by: '原文支持', precedes: '前置于' }

export function checkedMap(value: StudyMap): StudyMap {
  if (value?.version !== 'study-map-v1' || !Array.isArray(value.nodes) || !Array.isArray(value.edges) || value.nodes.length > 121 || value.edges.length > 180) throw new Error('梳理图格式无效')
  const ids = new Set<string>()
  for (const node of value.nodes) {
    if (!/^(root|[cqs][0-9]+)$/.test(node.id) || ids.has(node.id) || typeof node.label !== 'string' || node.label.length > 120 || !['topic', 'concept', 'question', 'source'].includes(node.kind)) throw new Error('梳理图节点无效')
    ids.add(node.id)
  }
  for (const edge of value.edges) if (!ids.has(edge.source) || !ids.has(edge.target) || !Object.prototype.hasOwnProperty.call(edgeLabels, edge.relation)) throw new Error('梳理图关系无效')
  return value
}

export function diagramView(data: StudyMap, mode: MapMode, conceptId = ''): StudyMap {
  checkedMap(data)
  const questions = new Set(data.nodes.filter(n => n.kind === 'question' && (mode !== 'wrong' || n.state === 'wrong') && (!conceptId || data.edges.some(e => e.source === conceptId && e.target === n.id))).map(n => n.id))
  if (!questions.size) return { ...data, nodes: [], edges: [] }
  const included = new Set(['root', ...questions])
  for (const edge of data.edges) {
    if (questions.has(edge.target)) included.add(edge.source)
    if (questions.has(edge.source) && mode !== 'outline') included.add(edge.target)
  }
  return { ...data, nodes: data.nodes.filter(n => included.has(n.id)), edges: data.edges.filter(e => included.has(e.source) && included.has(e.target)) }
}

export function mermaidSource(data: StudyMap) {
  checkedMap(data)
  // Labels are plain display text, never Mermaid directives, HTML or Markdown. Exact text stays in the node list.
  const replacements: Record<string, string> = { '"': '＂', '<': '〈', '>': '〉', '[': '［', ']': '］', '{': '｛', '}': '｝', '%': '％', '#': '＃', '&': '＆', '`': '｀', '|': '｜', '\\': '＼' }
  const encode = (label: string) => (label.length > 32 ? label.slice(0, 31) + '…' : label).replace(/[\r\n\t]/g, ' ').replace(/["<>\[\]{}%#&`|\\]/g, char => replacements[char])
  const lines = ['flowchart TB', ...data.nodes.map(node => `  ${node.id}["${encode(node.label)}"]`),
    ...data.edges.map(edge => `  ${edge.source} -->|${edgeLabels[edge.relation]}| ${edge.target}`),
    '  classDef wrong fill:#fff0f1,stroke:#a23f52,color:#612331',
    '  classDef correct fill:#eaf5ef,stroke:#43765c,color:#234c37']
  for (const node of data.nodes) if (node.state === 'wrong' || node.state === 'correct') lines.push(`  class ${node.id} ${node.state}`)
  return lines.join('\n')
}
