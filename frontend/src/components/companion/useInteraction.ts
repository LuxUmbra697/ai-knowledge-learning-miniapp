import { useEffect, useRef, useState } from 'react'
import Taro, { useDidHide } from '@tarojs/taro'
import { useStudio } from '../StudioProvider'
import { Gesture } from './gesture'

export function useInteraction(react: () => void, active = true) {
  const { companionForm } = useStudio()
  const gesture = useRef(new Gesture()), timer = useRef<ReturnType<typeof setTimeout>>()
  const reactRef = useRef(react); reactRef.current = react
  const [menu, setMenu] = useState(false)
  const [reaction, setReaction] = useState('idle')
  const reactionTimer = useRef<ReturnType<typeof setTimeout>>()
  const name = companionForm === 'orange' ? '秋庭澄' : '樱野小满'
  const openChat = () => Taro.navigateTo({ url: `/learning/companion/index?character=${companionForm}` })
  const openActions = async (onHide: () => void) => {
    setMenu(false)
    try {
      const result = await Taro.showActionSheet({ itemList: [`和${name}聊天`, '收起伙伴'] })
      if (result.tapIndex === 0) openChat()
      if (result.tapIndex === 1) onHide()
    } catch { /* Dismissing the action sheet leaves the companion unchanged. */ }
  }
  const feedback = (kind: 'tap' | 'drag' | 'held') => {
    reactRef.current(); setReaction(kind); clearTimeout(reactionTimer.current)
    reactionTimer.current = setTimeout(() => setReaction('idle'), 1600)
    if (kind !== 'drag') Taro.showToast({ title: companionForm === 'orange'
      ? kind === 'held' ? '嗯，我在听。慢慢说。' : '这一页，也一起看看吧。'
      : kind === 'held' ? '呀，被你发现我在发呆啦。' : '今天也留一枚小书签吧！', icon: 'none', duration: 1500 })
  }
  const invite = async () => {
    const result = await Taro.showModal({ title: `${name}的小邀请`, content: companionForm === 'orange' ? '窗边还空着。要过来聊一会儿吗？' : '修书台旁有个空位，要来坐坐吗？', confirmText: '去聊一会', cancelText: '下次再聊' })
    if (result.confirm) openChat()
  }
  const cancel = () => { clearTimeout(timer.current); gesture.current.cancel() }
  useEffect(() => { if (!active) cancel() }, [active])
  useDidHide(cancel)
  useEffect(() => () => { cancel(); clearTimeout(reactionTimer.current) }, [])
  return { menu, reaction, name, openChat, openActions, invite, cancel,
    start: (x: number, y: number) => {
      cancel(); gesture.current.start(x, y, Date.now())
      timer.current = setTimeout(() => {
        const outcome = gesture.current.hold(Date.now())
        if (outcome) { feedback('held'); setMenu(true); if (outcome === 'invite') void invite() }
      }, 620)
    },
    move: (x: number, y: number) => { const dragged = gesture.current.move(x, y); if (dragged) clearTimeout(timer.current); return dragged },
    end: (x: number, y: number) => {
      clearTimeout(timer.current)
      const outcome = gesture.current.end(x, y, Date.now())
      if (outcome === 'tap') { feedback('tap'); setMenu(value => !value) }
      if (outcome === 'drag') { feedback('drag'); setMenu(false) }
      return outcome
    },
  }
}
