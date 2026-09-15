import { ReactNode, useState, useRef, useEffect } from 'react'
import { MovableArea, MovableView, Image, Button, View } from '@tarojs/components'
import Taro, { useDidHide, useDidShow, usePageScroll } from '@tarojs/taro'
import { clampPosition, safePosition, companionSize } from './position'
import { useCompanion } from './useCompanion'
import { useInteraction } from './useInteraction'
import { Icon } from '../Icon'

const pointOf = (event: unknown) => (event as { touches?: { clientX: number; clientY: number }[] }).touches?.[0]

export default function Companion({ reducedMotion, onHide, onSafeChange, layout }: { reducedMotion: boolean; onHide: () => void; onSafeChange: (safe: boolean) => void; layout?: ReactNode }) {
  const info = Taro.getWindowInfo()
  const saved = Taro.getStorageSync('ai-learn:v1:companion-position') || { x: info.windowWidth - companionSize.width - 4, y: 120 }
  const [position, setPosition] = useState(() => clampPosition(saved, info.windowWidth, info.windowHeight))
  const live = useRef(position)
  const touch = useRef({ x: 0, y: 0 })
  const [visible, setVisible] = useState(true)
  const [safe, setSafe] = useState(true)
  useEffect(() => onSafeChange(safe), [safe, onSafeChange])
  const state = useCompanion(visible && safe)
  const interaction = useInteraction(state.nextPose, visible && safe)
  const place = () => {
    const next = Taro.getWindowInfo()
    Taro.createSelectorQuery().selectAll('.primary-button, .secondary-button, .text-button, .icon-button, .answer-option, .studio-input, .studio-textarea, .mobile-navigation, .stat, .page-title, .page-subtitle, .welcome-title, .section-title, .row-title, .field-hint, .question-stem, .answer-explanation, .claim-text, .notebook-toolbar, .diagnosis-picker, .diagram-surface, .map-toolbar').boundingClientRect(rectangles => {
      const candidate = safePosition(live.current, next.windowWidth, next.windowHeight, Array.isArray(rectangles) ? rectangles : [])
      setSafe(!!candidate)
      if (candidate) { live.current = candidate; setPosition(previous => previous.x === candidate.x && previous.y === candidate.y ? previous : candidate) }
    }).exec()
  }
  const scrollTimer = useRef<ReturnType<typeof setTimeout>>()
  usePageScroll(() => { if (!scrollTimer.current) scrollTimer.current = setTimeout(() => { scrollTimer.current = undefined; place() }, 80) })
  useEffect(() => { const timer = setTimeout(place, 40); return () => clearTimeout(timer) }, [layout])
  useDidHide(() => setVisible(false))
  useDidShow(() => { setVisible(true); place() })
  useEffect(() => {
    const resize = place
    const keyboard = (event: { height: number }) => setVisible(event.height === 0)
    Taro.onWindowResize(resize)
    Taro.onKeyboardHeightChange(keyboard)
    const timer = setTimeout(place, 500)
    return () => { clearTimeout(timer); clearTimeout(scrollTimer.current); Taro.offWindowResize(resize); Taro.offKeyboardHeightChange(keyboard) }
  }, [])
  if (!visible) return null
  return <MovableArea className='companion-area' style={{ visibility: safe ? 'visible' : 'hidden' }}><MovableView className={`companion-native pose-${state.pose} ${reducedMotion || !state.enabled ? '' : 'companion-animated'}`} direction='all' x={position.x} y={position.y} inertia={false}
    onChange={event => { live.current = { x: event.detail.x, y: event.detail.y } }}
    onTouchStart={event => { const point = pointOf(event); if (point) { touch.current = { x: point.clientX, y: point.clientY }; interaction.start(point.clientX, point.clientY) } }}
    onTouchMove={event => { const point = pointOf(event); if (point) { touch.current = { x: point.clientX, y: point.clientY }; interaction.move(point.clientX, point.clientY) } }}
    onTouchCancel={interaction.cancel}
    onTouchEnd={() => {
      interaction.end(touch.current.x, touch.current.y)
      const current = Taro.getWindowInfo()
      const next = clampPosition(live.current, current.windowWidth, current.windowHeight)
      live.current = next; setPosition(next); Taro.setStorageSync('ai-learn:v1:companion-position', next)
      place()
    }}>
    <Image src={state.source} mode='aspectFit' />{interaction.menu && <Button className='companion-action' aria-label='伙伴操作' onTouchStart={event => event.stopPropagation()} onTouchEnd={event => event.stopPropagation()} onClick={event => { event.stopPropagation(); void interaction.openActions(onHide) }}><View className='companion-action-mark'><Icon name='more' size={14} /></View></Button>}
  </MovableView></MovableArea>
}
