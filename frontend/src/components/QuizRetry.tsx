import { useRef, useState } from 'react'
import { Button, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { LearningTask, retryQuizTask } from '../services/api'
import { Icon } from './Icon'
import { Notice } from './StudioShell'

export function QuizAttempts({ task }: { task: LearningTask }) {
  return task.generation ? <Text className='muted'>生成尝试 {task.generation.attempts} / {task.generation.max_attempts}</Text> : null
}

export function QuizRetry({ task, replace = false }: { task: LearningTask; replace?: boolean }) {
  const lock = useRef(false), [busy, setBusy] = useState(false), [error, setError] = useState('')
  if (task.kind !== 'quiz' || !['failed', 'cancelled'].includes(task.status)) return null
  const retry = async () => {
    if (lock.current) return
    lock.current = true
    try {
      const result = await Taro.showModal({ title: '重新生成练习', content: '保留原主题与题型数量，最多尝试 10 次。模型调用可能产生费用；连续点击不会重复创建任务。' })
      if (!result.confirm) return
      setBusy(true); setError('')
      const next = await retryQuizTask(task.task_id)
      const url = `/pages/quiz/index?taskId=${encodeURIComponent(next.task_id)}`
      if (replace) await Taro.redirectTo({ url })
      else await Taro.navigateTo({ url })
    } catch (reason) { setError(reason instanceof Error ? reason.message : '重新生成未提交成功，请再试一次') }
    finally { lock.current = false; setBusy(false) }
  }
  return <View className='quiz-retry'>
    <Button className='text-button' disabled={busy} onClick={retry}><Icon name='refresh' size={16} />{busy ? '正在提交' : '重新生成'}</Button>
    {error && <Notice message={error} />}
  </View>
}
