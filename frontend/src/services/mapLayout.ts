import * as dagre from '@dagrejs/dagre'
import { checkedMap, type StudyMap } from './learningMap'

export function layoutMap(data: StudyMap) {
  checkedMap(data)
  const graph = new dagre.graphlib.Graph().setGraph({ rankdir: 'TB', nodesep: 24, ranksep: 56, marginx: 16, marginy: 16 }).setDefaultEdgeLabel(() => ({}))
  for (const node of data.nodes) graph.setNode(node.id, { width: 172, height: 64 })
  for (const edge of data.edges) graph.setEdge(edge.source, edge.target)
  dagre.layout(graph)
  return { width: graph.graph().width || 1, height: graph.graph().height || 1,
    nodes: data.nodes.map(node => ({ ...node, ...graph.node(node.id) })),
    edges: data.edges.map(edge => ({ ...edge, points: graph.edge(edge.source, edge.target).points as { x: number; y: number }[] })),
  }
}
