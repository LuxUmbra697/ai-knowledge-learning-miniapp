import { useEffect, useMemo, useRef, useState } from 'react'
import { View, Text, Button, Picker } from '@tarojs/components'
import Taro, { useDidHide, useDidShow } from '@tarojs/taro'
import { request } from '../../services/api'
import { PollControl } from '../../services/polling'
import { checkedMap, diagramView, mermaidSource, type StudyMap, type MapMode } from '../../services/learningMap'
import { Notice } from '../StudioShell'
import { Icon } from '../Icon'
import Diagram from './Diagram'

export default function LearningMap({ quizId }: { quizId: string }) {
  const [data, setData] = useState<StudyMap | null>(null), [error, setError] = useState(''), [mode, setMode] = useState<MapMode>('outline')
  const [concept, setConcept] = useState('')
  const control = useRef<PollControl>(), mounted = useRef(true)
  const load = async () => {
    control.current?.cancel(); const current = new PollControl(); control.current = current; setError('')
    try { const result = checkedMap(await request<StudyMap>(`/quiz/${quizId}/maps`, { control: current })); if (mounted.current && !current.cancelled) setData(result) }
    catch (reason) { if (mounted.current && !current.cancelled) setError(reason instanceof Error ? reason.message : '梳理图读取失败') }
  }
  useEffect(() => { mounted.current = true; void load(); return () => { mounted.current = false; control.current?.cancel() } }, [quizId])
  useDidHide(() => control.current?.cancel())
  useDidShow(() => { if (!data && control.current?.cancelled) void load() })
  const graph = useMemo(() => data ? diagramView(data, mode, concept) : null, [data, mode, concept])
  const concepts = data?.nodes.filter(n => n.kind === 'concept') || []
  return <View className='learning-map'>
    <Text className='section-title'>学习内容梳理</Text>
    <Text className='muted'>依据本次题目知识点标签和作答记录整理，标签尚未经人工确认；连线不代表先修要求。</Text>
    {error && <Notice message={error} retry={load} />}
    {!data && !error && <Text className='muted'>正在读取学习关系</Text>}
    {graph && <>
      <View className='map-tabs'>{([['outline', '内容梳理'], ['network', '关系网络'], ['wrong', '错题复盘']] as const).map(([key, label]) => <Button key={key} className={`text-button ${mode === key ? 'active' : ''}`} onClick={() => setMode(key)}>{label}</Button>)}</View>
      <View className='map-toolbar'><Picker mode='selector' range={['全部知识点', ...concepts.map(n => n.label)]} value={Math.max(0, concepts.findIndex(n => n.id === concept) + 1)} onChange={event => setConcept(concepts[Number(event.detail.value) - 1]?.id || '')}><View className='secondary-button'>{concepts.find(n => n.id === concept)?.label || '全部知识点'}</View></Picker>
        <Button className='text-button' disabled={!graph.nodes.length} onClick={async () => { try { await Taro.setClipboardData({ data: mermaidSource(graph) }) } catch { setError('复制失败，请稍后重试') } }}><Icon name='report' size={16} />复制 Mermaid</Button>
      </View>
      {graph.nodes.length ? <Diagram data={graph} /> : <View className='empty-state'><Text>本次所选知识点没有错题</Text></View>}
      <View className='map-node-list'>{graph.nodes.filter(n => n.kind === 'question' || n.kind === 'source').map(node => <View className={`map-node ${node.state || ''}`} key={node.id}>
        <Text className='row-title'>{node.label}</Text>{node.detail && <Text>{node.detail}</Text>}
        {node.kind === 'question' && <Button className='text-button' onClick={() => Taro.navigateTo({ url: `/pages/quiz/index?quizId=${quizId}&questionId=${encodeURIComponent(node.question_id || '')}` })}>查看作答解析</Button>}
        {node.kind === 'source' && node.doc_id && node.chunk_id && <Button className='text-button' onClick={() => Taro.navigateTo({ url: `/learning/document/index?docId=${encodeURIComponent(node.doc_id!)}&chunkId=${encodeURIComponent(node.chunk_id!)}&revision=${node.revision}` })}><Icon name='book' size={16} />查看原文</Button>}
      </View>)}</View>
    </>}
  </View>
}
