import { useEffect, useState } from 'react'
import { View, Text, Slider, Button } from '@tarojs/components'
import { mermaidSource, type StudyMap } from '../../services/learningMap'
import { useStudio } from '../StudioProvider'

let sequence = 0
export default function Diagram({ data }: { data: StudyMap }) {
  const { theme } = useStudio()
  const [result, setResult] = useState<{ url: string; width: number } | null>(null), [error, setError] = useState('')
  const [zoom, setZoom] = useState(100), [retry, setRetry] = useState(0)
  useEffect(() => {
    let live = true, url = ''
    const container = document.createElement('div')
    container.style.cssText = 'position:absolute;left:-20000px;top:0;visibility:hidden;pointer-events:none'
    document.body.appendChild(container)
    setResult(null); setError('')
    const render = async () => {
      try {
        const [{ default: mermaid }, { default: purify }] = await Promise.all([import('mermaid'), import('dompurify')])
        if (!live) return
        mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', htmlLabels: false, maxTextSize: 100000,
          maxEdges: 180, theme: theme === 'night' ? 'dark' : 'neutral', fontFamily: 'sans-serif',
          flowchart: { useMaxWidth: false, htmlLabels: false, curve: 'linear', padding: 14 } })
        const { svg } = await mermaid.render(`studyDiagram${++sequence}`, mermaidSource(data), container)
        const clean = purify.sanitize(svg, { USE_PROFILES: { svg: true, svgFilters: true }, FORBID_TAGS: ['foreignObject', 'a', 'image', 'script', 'iframe'], FORBID_ATTR: ['href', 'xlink:href'] })
        const parsed = new DOMParser().parseFromString(clean, 'image/svg+xml').documentElement
        const bounds = parsed.getAttribute('viewBox')?.split(/\s+/).map(Number)
        if (parsed.tagName !== 'svg' || !bounds || bounds.length !== 4 || !bounds.every(Number.isFinite) || bounds[2] <= 0) throw new Error('invalid_svg')
        url = URL.createObjectURL(new Blob([clean], { type: 'image/svg+xml' }))
        if (live) setResult({ url, width: bounds[2] })
        else URL.revokeObjectURL(url)
      } catch { if (live) setError('图形暂未绘制成功，学习记录和解析仍然可查看') }
      finally { container.remove() }
    }
    void render()
    return () => { live = false; container.remove(); if (url) URL.revokeObjectURL(url) }
  }, [data, theme, retry])
  return <View className='diagram-surface'>
    {error ? <View className='notice'><Text>{error}</Text><Button className='text-button' onClick={() => setRetry(n => n + 1)}>重试绘图</Button></View> : !result ? <Text className='muted'>正在绘制学习梳理图</Text> : <>
      <View className='map-zoom'><Text className='muted'>缩放 {zoom}%</Text><Slider min={50} max={200} step={25} value={zoom} onChange={event => setZoom(event.detail.value)} /></View>
      <div className='map-viewport' tabIndex={0} role='region' aria-label='学习关系图'><img className='map-image' alt='学习知识点与作答关系图' src={result.url} style={{ width: `${result.width * zoom / 100}px` }} /></div>
    </>}
  </View>
}
