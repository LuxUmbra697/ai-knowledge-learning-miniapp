import { ReactNode, useState, useRef, useEffect } from 'react'
import { MovableArea, MovableView, Image, Button } from '@tarojs/components'
import Taro, { useDidHide, useDidShow, usePageScroll } from '@tarojs/taro'
import { dockPosition, safePosition } from './position'
import { useCompanion } from './useCompanion'

export default function Companion({ reducedMotion, onHide, onSafeChange, layout }: { reducedMotion: boolean; onHide: () => void; onSafeChange: (safe: boolean) => void; layout?: ReactNode }) {
  const info = Taro.getWindowInfo()
  const saved = Taro.getStorageSync('ai-learn:v1:companion-position') || { x: info.windowWidth - 82, y: 120 }
  const [position, setPosition] = useState(() => dockPosition(saved, info.windowWidth, info.windowHeight))
  const live = useRef(position)
  const start = useRef(position)
  const [menu, setMenu] = useState(false)
  const [visible, setVisible] = useState(true)
  const [safe, setSafe] = useState(true)
  useEffect(() => onSafeChange(safe), [safe, onSafeChange])
  const state = useCompanion(visible && safe)
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
    onTouchStart={() => { start.current = live.current }}
    onTouchEnd={() => {
      if (Math.hypot(live.current.x - start.current.x, live.current.y - start.current.y) < 6) { setMenu(value => !value); state.nextPose() }
      const current = Taro.getWindowInfo()
      const next = dockPosition(live.current, current.windowWidth, current.windowHeight)
      setPosition(next); Taro.setStorageSync('ai-learn:v1:companion-position', next)
      place()
    }}>
    <Image src={state.source} mode='aspectFit' />{menu && <Button className='companion-hide' onClick={onHide}>收起伙伴</Button>}
  </MovableView></MovableArea>
}
