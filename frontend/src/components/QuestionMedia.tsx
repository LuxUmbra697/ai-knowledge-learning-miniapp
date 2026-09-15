import { useEffect, useRef, useState } from 'react'
import { View, Text, Image, Button } from '@tarojs/components'
import Taro, { useDidShow, useDidHide } from '@tarojs/taro'
import { getQuizImage, cancelLearningTask, QuizImage } from '../services/api'
import { PollControl, pollUntil } from '../services/polling'
import { taskPhase } from '../services/taskDisplay'
import { Icon } from './Icon'

export function QuestionMedia({ assetId, legacyUrl, revealed }: { assetId?: string | null; legacyUrl?: string | null; revealed: boolean }) {
  const [asset, setAsset] = useState<QuizImage | null>(null), [error, setError] = useState('')
  const control = useRef<PollControl>(), live = useRef(true)
  const load = async () => {
    control.current?.cancel()
    if (!assetId || !live.current) return
    const current = new PollControl(); control.current = current
    setError('')
    try {
      await pollUntil(() => getQuizImage(assetId, current), value => {
        if (!current.cancelled && live.current) setAsset(value)
        return ['ready', 'failed', 'locked'].includes(value.status)
      }, { control: current, intervalMs: 2500, maxAttempts: 80 })
    } catch (reason) { if (!current.cancelled && live.current) setError(reason instanceof Error ? reason.message : '配图读取失败') }
  }
  useEffect(() => { live.current = true; setAsset(null); load(); return () => { live.current = false; control.current?.cancel() } }, [assetId, revealed])
  useDidHide(() => { live.current = false; control.current?.cancel() })
  useDidShow(() => { live.current = true; load() })
  const cancel = async () => {
    if (!asset) return
    const result = await Taro.showModal({ title: '取消配图', content: '文字题库会保留。已经开始的配图调用可能仍会产生费用。' })
    if (!result.confirm) return
    try { await cancelLearningTask(asset.task_id); if (live.current) load() }
    catch (reason) { if (live.current) setError(reason instanceof Error ? reason.message : '取消失败') }
  }
  if (!assetId && !legacyUrl) return null
  const url = revealed ? assetId ? asset?.url : legacyUrl : null
  const pending = !!asset && !['ready', 'failed', 'locked'].includes(asset.status)
  return <View className={`illustration ${url && !error ? '' : 'illustration-status'}`}>
    <View className='illustration-frame'>
      {url && /^https:\/\//.test(url) && !error ? <Image className='question-media' src={url} mode='aspectFit' onError={() => { if (live.current) setError('图片未能加载，可重新读取短期访问链接') }} /> : <Text className='muted'>{error || asset?.message || (asset ? taskPhase(asset.stage) : '正在读取配图状态')}</Text>}
    </View>
    <View className='illustration-controls'><Text className='field-hint'>AI 示意图 · 非答案证据</Text>{pending && <Button className='text-button' onClick={cancel}><Icon name='close' size={16} />取消配图</Button>}{error && assetId && <Button className='text-button' onClick={load}><Icon name='refresh' size={16} />重新读取配图</Button>}</View>
  </View>
}
