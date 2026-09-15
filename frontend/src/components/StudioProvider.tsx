import { createContext, useContext, useState, PropsWithChildren } from 'react'
import Taro from '@tarojs/taro'

export const themes = [
  { id: 'sakura', name: '樱花学园', accent: '#b74b6c', paper: '#fff6f9', motif: '花笺' },
  { id: 'night', name: '月夜观测室', accent: '#a3ddd1', paper: '#202729', motif: '星图' },
  { id: 'sea', name: '海盐夏日', accent: '#197c95', paper: '#eefbfc', motif: '航线' },
  { id: 'forest', name: '森之图书馆', accent: '#326b55', paper: '#f1f7f2', motif: '藏书' },
  { id: 'scroll', name: '赤金绘卷', accent: '#a73a38', paper: '#fff7ed', motif: '印记' },
] as const
type Settings = { theme: string; reducedMotion: boolean; companion: boolean; companionFolded: boolean; companionForm: 'pink' | 'orange'; companionPose: 'auto' | 'read' | 'wave' | 'celebrate' }
const defaults: Settings = { theme: 'sakura', reducedMotion: false, companion: true, companionFolded: false, companionForm: 'pink', companionPose: 'auto' }
const StudioContext = createContext({ ...defaults, update: (_value: Partial<Settings>) => {} })

export function StudioProvider({ children }: PropsWithChildren) {
  const [settings, setSettings] = useState<Settings>(() => {
    const saved = Taro.getStorageSync('ai-learn:v1:appearance') || {}
    return { ...defaults, theme: themes.some(t => t.id === saved.theme) ? saved.theme : defaults.theme,
      reducedMotion: saved.reducedMotion === true, companion: saved.companion !== false,
      companionFolded: saved.companionFolded === true,
      companionForm: saved.companionForm === 'orange' ? 'orange' : 'pink',
      companionPose: ['auto', 'read', 'wave', 'celebrate'].includes(saved.companionPose) ? saved.companionPose : 'auto' }
  })
  const update = (value: Partial<Settings>) => setSettings(previous => {
    const next = { ...previous, ...value }
    Taro.setStorageSync('ai-learn:v1:appearance', next)
    return next
  })
  return <StudioContext.Provider value={{ ...settings, update }}>{children}</StudioContext.Provider>
}

export const useStudio = () => useContext(StudioContext)
