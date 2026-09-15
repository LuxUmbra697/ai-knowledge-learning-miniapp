import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, Slider, View, Text } from '@tarojs/components'
import Taro, { useDidHide, useDidShow } from '@tarojs/taro'
import { layoutMap } from '../../services/mapLayout'
import { type StudyMap } from '../../services/learningMap'
import { useStudio } from '../StudioProvider'

let counter = 0
export default function Diagram({ data }: { data: StudyMap }) {
  const { theme } = useStudio()
  const id = useRef(`study_canvas_${++counter}`), canvas = useRef<any>(), pending = useRef<any>()
  const [width, setWidth] = useState(() => Math.max(240, Math.min(720, Taro.getWindowInfo().windowWidth - 40)))
  const [zoom, setZoom] = useState(100), [error, setError] = useState('')
  const layout = useMemo(() => layoutMap(data), [data])
  const offset = useRef({ x: 0, y: 0 }), gesture = useRef({ x: 0, y: 0, originX: 0, originY: 0 })
  const height = 380
  const paint = () => {
    const node = canvas.current
    if (!node) return
    const ctx = node.getContext('2d'), scale = zoom / 100, night = theme === 'night'
    ctx.clearRect(0, 0, width, height); ctx.fillStyle = night ? '#293234' : '#ffffff'; ctx.fillRect(0, 0, width, height)
    ctx.save(); ctx.translate(offset.current.x, offset.current.y); ctx.scale(scale, scale)
    ctx.strokeStyle = night ? '#aebfbc' : '#75897d'; ctx.lineWidth = 1.5
    for (const edge of layout.edges) {
      ctx.beginPath(); edge.points.forEach((point, i) => i ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y)); ctx.stroke()
      const last = edge.points[edge.points.length - 1]
      ctx.beginPath(); ctx.moveTo(last.x - 4, last.y - 7); ctx.lineTo(last.x, last.y); ctx.lineTo(last.x + 4, last.y - 7); ctx.stroke()
    }
    ctx.font = '13px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
    for (const item of layout.nodes) {
      ctx.fillStyle = item.state === 'wrong' ? '#fff0f1' : item.state === 'correct' ? '#eaf5ef' : night ? '#354844' : '#f7f9f6'
      ctx.fillRect(item.x - 86, item.y - 32, 172, 64); ctx.strokeRect(item.x - 86, item.y - 32, 172, 64)
      ctx.fillStyle = item.state === 'wrong' ? '#612331' : item.state === 'correct' ? '#234c37' : night ? '#f0f4ef' : '#304039'
      const chars = Array.from(item.label)
      ctx.fillText(chars.slice(0, 11).join(''), item.x, item.y - (chars.length > 11 ? 10 : 0), 152)
      if (chars.length > 11) ctx.fillText(chars.slice(11, 21).join('') + (chars.length > 21 ? '…' : ''), item.x, item.y + 12, 152)
    }
    ctx.restore()
  }
  const stop = () => { if (pending.current) canvas.current?.cancelAnimationFrame(pending.current); pending.current = undefined }
  useDidHide(stop)
  useDidShow(() => paint())
  useEffect(() => {
    const resize = () => setWidth(Math.max(240, Math.min(720, Taro.getWindowInfo().windowWidth - 40)))
    Taro.onWindowResize(resize)
    return () => { Taro.offWindowResize(resize); stop() }
  }, [])
  useEffect(() => {
    let active = true
    stop(); setError(''); offset.current = { x: width / 2 - (layout.nodes[0]?.x || 0), y: 12 }
    Taro.nextTick(() => Taro.createSelectorQuery().select(`#${id.current}`).fields({ node: true, size: true }).exec(result => {
      if (!active) return
      const node = result?.[0]?.node
      if (!node) { setError('图形暂不可用，下面仍可查看完整知识点和解析'); return }
      canvas.current = node; node.width = width; node.height = height; paint()
    }))
    return () => { active = false; stop() }
  }, [layout, width, theme, zoom])
  return <View className='diagram-surface'>
    {error && <Text className='muted'>{error}</Text>}
    <View className='map-zoom'><Text className='muted'>缩放 {zoom}%</Text><Slider min={50} max={200} step={25} value={zoom} onChange={event => setZoom(event.detail.value)} /></View>
    <Canvas id={id.current} canvasId={id.current} type='2d' style={{ width: `${width}px`, height: `${height}px` }}
      onTouchStart={event => { const touch = event.touches[0]; gesture.current = { x: touch.x, y: touch.y, originX: offset.current.x, originY: offset.current.y } }}
      onTouchMove={event => { const touch = event.touches[0], scale = zoom / 100; offset.current = {
        x: Math.max(40 - layout.width * scale, Math.min(width - 40, gesture.current.originX + touch.x - gesture.current.x)),
        y: Math.max(40 - layout.height * scale, Math.min(height - 40, gesture.current.originY + touch.y - gesture.current.y)),
      }; if (!pending.current && canvas.current) pending.current = canvas.current.requestAnimationFrame(() => { pending.current = undefined; paint() }) }}
      onTouchEnd={event => { const touch = event.changedTouches[0]; if (!touch || Math.hypot(touch.x - gesture.current.x, touch.y - gesture.current.y) > 6) return
        const scale = zoom / 100, x = (touch.x - offset.current.x) / scale, y = (touch.y - offset.current.y) / scale
        const item = layout.nodes.find(n => Math.abs(n.x - x) <= 86 && Math.abs(n.y - y) <= 32)
        if (item) void Taro.showModal({ title: item.label.slice(0, 32), content: item.detail || item.label, showCancel: false })
      }} />
  </View>
}
