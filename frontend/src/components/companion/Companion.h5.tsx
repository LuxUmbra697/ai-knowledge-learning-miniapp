import { ReactNode, useEffect, useRef, useState } from 'react'
import Taro from '@tarojs/taro'
import { clampPosition, safePosition, companionSize } from './position'
import { useCompanion } from './useCompanion'
import { useInteraction } from './useInteraction'
import { Icon } from '../Icon'
const storageKey = 'ai-learn:v1:companion-position'

export default function Companion({ reducedMotion, onHide, onSafeChange, layout }: { reducedMotion: boolean; onHide: () => void; onSafeChange: (safe: boolean) => void; layout?: ReactNode }) {
  const element = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(true)
  const [safe, setSafe] = useState(true)
  useEffect(() => onSafeChange(safe), [safe, onSafeChange])
  const state = useCompanion(visible && safe)
  const interaction = useInteraction(state.nextPose, visible && safe)
  const position = useRef({ x: 0, y: 120 })
  const dragging = useRef<{ x: number; y: number; startX: number; startY: number } | null>(null)
  const place = () => {
    if (dragging.current) return
    const boxes = [...document.querySelectorAll('taro-button-core, input, textarea, .mobile-navigation, .stat, .page-title, .page-subtitle, .welcome-title, .section-title, .row-title, .field-hint, .question-stem, .answer-explanation, .claim-text, .notebook-toolbar, .diagnosis-picker, .diagram-surface, .map-toolbar')]
      .filter(node => !node.closest('.companion') && node.getClientRects().length > 0)
      .map(node => node.getBoundingClientRect()).filter(box => box.width > 0 && box.height > 0)
    const next = safePosition(position.current, window.innerWidth, window.innerHeight, boxes)
    setSafe(!!next)
    if (!next) return
    position.current = next
    if (element.current) element.current.style.transform = `translate(${next.x}px, ${next.y}px)`
  }
  useEffect(() => { const timer = setTimeout(place, 40); return () => clearTimeout(timer) }, [layout])
  useEffect(() => {
    const restore = () => {
      position.current = clampPosition(Taro.getStorageSync(storageKey) || { x: window.innerWidth - companionSize.width - 4, y: 120 }, window.innerWidth, window.innerHeight)
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
    const observer = new MutationObserver(records => {
      if (records.some(record => !(record.target as Element).closest?.('.companion, .companion-reserved'))) scroll()
    })
    observer.observe(document.body, { childList: true, characterData: true, subtree: true })
    document.addEventListener('scroll', scroll, true)
    const timer = setTimeout(place, 500)
    return () => { observer.disconnect(); clearTimeout(timer); cancelAnimationFrame(frame); document.removeEventListener('scroll', scroll, true); window.removeEventListener('resize', restore); document.removeEventListener('visibilitychange', visibility); document.removeEventListener('focusin', focus); document.removeEventListener('focusout', blur) }
  }, [])
  return <div ref={element} data-form={Taro.getStorageSync('ai-learn:v1:appearance')?.companionForm || 'pink'} data-pose={state.pose} data-reaction={interaction.reaction} className={`companion pose-${state.pose} ${reducedMotion || !state.enabled ? '' : 'companion-animated'}`} style={{ visibility: visible && safe && state.visible ? 'visible' : 'hidden' }}
    role='button' tabIndex={0} aria-label={`${interaction.name}，学习伙伴`}
    onKeyDown={event => { if (event.target === event.currentTarget && ['Enter', ' '].includes(event.key)) { event.preventDefault(); interaction.start(0, 0); interaction.end(0, 0) } }}
    onContextMenu={e => e.preventDefault()}
    onPointerDown={e => {
      if (!e.isPrimary || e.button !== 0 || (e.target as HTMLElement).closest('button')) return
      e.currentTarget.setPointerCapture(e.pointerId)
      dragging.current = { x: e.clientX, y: e.clientY, startX: position.current.x, startY: position.current.y }
      interaction.start(e.clientX, e.clientY)
    }}
    onPointerMove={e => {
      if (!dragging.current) return
      const start = dragging.current
      if (!interaction.move(e.clientX, e.clientY)) return
      position.current = clampPosition({ x: start.startX + e.clientX - start.x, y: start.startY + e.clientY - start.y }, window.innerWidth, window.innerHeight)
      e.currentTarget.style.transform = `translate(${position.current.x}px, ${position.current.y}px)`
    }}
    onPointerUp={e => {
      const start = dragging.current
      dragging.current = null
      if (!start) return
      interaction.end(e.clientX, e.clientY)
      place()
      e.currentTarget.style.transform = `translate(${position.current.x}px, ${position.current.y}px)`
      Taro.setStorageSync(storageKey, position.current)
    }} onPointerCancel={() => { dragging.current = null; interaction.cancel() }}>
    <img src={state.source} draggable={false} alt='学习伙伴' />
    {interaction.menu && <button className='companion-action' aria-label='伙伴操作' title='伙伴操作' onPointerDown={event => event.stopPropagation()} onClick={event => { event.stopPropagation(); void interaction.openActions(onHide) }}><span className='companion-action-mark'><Icon name='more' size={14} /></span></button>}
  </div>
}
