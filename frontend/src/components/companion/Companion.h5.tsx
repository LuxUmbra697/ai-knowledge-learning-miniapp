import { useEffect, useRef, useState } from 'react'
import Taro from '@tarojs/taro'
import { clampPosition, safePosition } from './position'
import { useCompanion } from './useCompanion'
const storageKey = 'ai-learn:v1:companion-position'

export default function Companion({ reducedMotion, onHide }: { reducedMotion: boolean; onHide: () => void }) {
  const element = useRef<HTMLDivElement>(null)
  const [menu, setMenu] = useState(false)
  const [visible, setVisible] = useState(true)
  const [safe, setSafe] = useState(true)
  const state = useCompanion(visible && safe)
  const position = useRef({ x: 0, y: 120 })
  const dragging = useRef<{ x: number; y: number; startX: number; startY: number } | null>(null)
  const place = () => {
    if (dragging.current) return
    const boxes = [...document.querySelectorAll('taro-button-core, input, textarea, .mobile-navigation, .stat, .page-title, .page-subtitle, .welcome-title, .section-title, .row-title, .field-hint')]
      .filter(node => !node.closest('.companion') && node.getClientRects().length > 0)
      .map(node => node.getBoundingClientRect()).filter(box => box.width > 0 && box.height > 0)
    const next = safePosition(position.current, window.innerWidth, window.innerHeight, boxes)
    setSafe(!!next)
    if (!next) return
    position.current = next
    if (element.current) element.current.style.transform = `translate(${next.x}px, ${next.y}px)`
  }
  useEffect(() => {
    const restore = () => {
      position.current = clampPosition(Taro.getStorageSync(storageKey) || { x: window.innerWidth - 82, y: 120 }, window.innerWidth, window.innerHeight)
      if (element.current) element.current.style.transform = `translate(${position.current.x}px, ${position.current.y}px)`
      place()
    }
    restore()
    const visibility = () => setVisible(!document.hidden)
    const focus = (event: FocusEvent) => setVisible(!['INPUT', 'TEXTAREA'].includes((event.target as HTMLElement)?.tagName))
    const blur = () => setVisible(!document.hidden)
    window.addEventListener('resize', restore)
    document.addEventListener('visibilitychange', visibility)
    document.addEventListener('focusin', focus)
    document.addEventListener('focusout', blur)
    let frame = 0
    const scroll = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(place) }
    document.addEventListener('scroll', scroll, true)
    const timer = setTimeout(place, 500)
    return () => { clearTimeout(timer); cancelAnimationFrame(frame); document.removeEventListener('scroll', scroll, true); window.removeEventListener('resize', restore); document.removeEventListener('visibilitychange', visibility); document.removeEventListener('focusin', focus); document.removeEventListener('focusout', blur) }
  }, [])
  return <div ref={element} data-form={Taro.getStorageSync('ai-learn:v1:appearance')?.companionForm || 'pink'} data-pose={state.pose} className={`companion pose-${state.pose} ${reducedMotion || !state.enabled ? '' : 'companion-animated'}`} style={{ visibility: visible && safe && state.visible ? 'visible' : 'hidden' }}
    onPointerDown={e => {
      if ((e.target as HTMLElement).closest('button')) return
      e.currentTarget.setPointerCapture(e.pointerId)
      dragging.current = { x: e.clientX, y: e.clientY, startX: position.current.x, startY: position.current.y }
    }}
    onPointerMove={e => {
      if (!dragging.current) return
      const start = dragging.current
      position.current = clampPosition({ x: start.startX + e.clientX - start.x, y: start.startY + e.clientY - start.y }, window.innerWidth, window.innerHeight)
      e.currentTarget.style.transform = `translate(${position.current.x}px, ${position.current.y}px)`
    }}
    onPointerUp={e => {
      const start = dragging.current
      dragging.current = null
      if (!start) return
      if (Math.hypot(e.clientX - start.x, e.clientY - start.y) < 6) { setMenu(value => !value); state.nextPose() }
      place()
      e.currentTarget.style.transform = `translate(${position.current.x}px, ${position.current.y}px)`
      Taro.setStorageSync(storageKey, position.current)
    }} onPointerCancel={() => { dragging.current = null }}>
    <img src={state.source} draggable={false} alt='学习伙伴' />
    {menu && <button className='companion-hide' onClick={onHide}>收起伙伴</button>}
  </div>
}
