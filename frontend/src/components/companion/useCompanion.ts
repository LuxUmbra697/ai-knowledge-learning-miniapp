import { useEffect, useState } from 'react'
import { useDidHide, useDidShow } from '@tarojs/taro'
import { useStudio } from '../StudioProvider'
import { companionFrames as frames } from '../../services/assets'
const poses = { read: 0, wave: 1, celebrate: 2 }

export function useCompanion(active = true) {
  const settings = useStudio()
  const [step, setStep] = useState(0)
  const [pageVisible, setPageVisible] = useState(true)
  useDidHide(() => setPageVisible(false))
  useDidShow(() => setPageVisible(true))
  const enabled = active && pageVisible && !settings.reducedMotion
  useEffect(() => {
    if (!enabled || settings.companionPose !== 'auto') return
    const timer = setTimeout(() => setStep(value => (value + 1) % 3), 9000)
    return () => clearTimeout(timer)
  }, [enabled, settings.companionPose, step])
  const pose = settings.companionPose === 'auto' ? step : poses[settings.companionPose]
  return { source: (frames[settings.companionForm] || frames.pink)[pose], pose, enabled,
    nextPose: () => setStep(value => (value + 1) % 3), visible: pageVisible }
}
