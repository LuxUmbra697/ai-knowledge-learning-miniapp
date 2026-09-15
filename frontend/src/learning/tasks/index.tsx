import { useRef, useState } from 'react'
import { View, Text, Button } from '@tarojs/components'
import Taro, { useDidHide, useDidShow } from '@tarojs/taro'
import { StudioShell, Notice, Empty, navigate } from '../../components/StudioShell'
import { Icon } from '../../components/Icon'
import { QuizRetry, QuizAttempts } from '../../components/QuizRetry'
import { cancelLearningTask, getLearningTasks, getToken, LearningTask, waitForLogin } from '../../services/api'
import { PollControl, pollUntil } from '../../services/polling'
import { taskPhase as phase } from '../../services/taskDisplay'

const statuses = { staging: '等待上传完成', queued: '等待处理', running: '处理中', completed: '已完成', failed: '未完成', cancelled: '已取消' }
const kinds = { index: '资料索引', answer: '知识问答', retrieve: '资料检索', quiz: '练习生成', report: '学习报告', cleanup: '资料清理', grade: '问答评阅', image: '练习配图', tutor: '逐步辅导', companion: '伙伴对话' }
export default function TasksPage() {
  const [tasks, setTasks] = useState<LearningTask[]>([]), [error, setError] = useState(''), [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(''), [busy, setBusy] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const live = useRef(true), control = useRef<PollControl>()
  const load = async (notify = false) => {
    await waitForLogin()
    if (!getToken()) { navigate('/pages/login/index'); return }
    control.current?.cancel(); const current = new PollControl(); control.current = current
    if (notify) setRefreshing(true)
    let first = true
    try {
      await pollUntil(() => getLearningTasks(current), result => {
        if (live.current && !current.cancelled) {
          setTasks(result.items); setLoading(false); setError(''); setRefreshing(false)
          if (notify && first) Taro.showToast({ title: '任务已刷新', icon: 'none' })
          first = false
        }
        return result.items.every(task => ['completed', 'failed', 'cancelled'].includes(task.status))
      }, { control: current, intervalMs: 3000, maxAttempts: 100 })
    } catch (reason) { if (live.current && !current.cancelled) setError(reason instanceof Error ? reason.message : '任务读取失败') }
    finally { if (live.current && !current.cancelled) { setLoading(false); setRefreshing(false) } }
  }
  useDidShow(() => { live.current = true; load() })
  useDidHide(() => { live.current = false; control.current?.cancel() })
  const cancel = async (task: LearningTask) => {
    if (busy) return
    const confirmed = await Taro.showModal({ title: '取消任务', content: '取消后不再发布新结果。已经开始的模型调用可能仍会产生费用。' })
    if (!confirmed.confirm) return
    setBusy(task.task_id)
    try {
      const result = await cancelLearningTask(task.task_id)
      if (live.current) setTasks(previous => previous.map(item => item.task_id === task.task_id ? result : item))
    } catch (reason) { if (live.current) setError(reason instanceof Error ? reason.message : '取消失败') }
    finally { if (live.current) setBusy('') }
  }
  return <StudioShell active='profile' title='任务记录' subtitle='每一次探索，都留下一份清晰的记录。'>
    <View className='section-heading'><Button className='text-button' onClick={() => navigate('/pages/profile/index')}>学习档案</Button><Button className='icon-button' aria-label='刷新任务' disabled={refreshing} onClick={() => load(true)}><Icon name='refresh' /></Button></View>
    {error && <Notice message={error} retry={() => load(true)} />}
    {!tasks.length && <Empty title={loading ? '正在读取任务' : '还没有任务记录'} text='添加资料后，可以在这里查看处理状态。' />}
    {tasks.map(task => <View className='task-entry' key={task.task_id}>
      <View className='task-heading'><View className='row-copy'><Text className='tiny-label'>{kinds[task.kind]}</Text><Text className='row-title'>{task.title || kinds[task.kind]}</Text><Text className='muted'>{task.created_at ? task.created_at.replace('T', ' ').replace('Z', ' UTC') : ''}</Text></View><Text className='tag'>{statuses[task.status]}</Text></View>
      {task.status === 'running' && <Text className='muted'>{phase(task.stage)}</Text>}
      <QuizAttempts task={task} />
      {task.error_message && <Notice message={task.error_message} />}
      {task.kind === 'image' && task.result?.notice && <Text className='muted'>{task.result.notice}</Text>}
      <View className='document-actions'><Button className='text-button' onClick={() => setSelected(selected === task.task_id ? '' : task.task_id)}><Icon name='clock' size={16} />{selected === task.task_id ? '收起记录' : '执行记录'}</Button>
        <QuizRetry task={task} />
        {!['completed', 'failed', 'cancelled'].includes(task.status) && <Button className='text-button' disabled={!!busy} onClick={() => cancel(task)}><Icon name='close' size={16} />取消任务</Button>}
        {task.kind === 'index' && task.result?.doc_id && task.status === 'completed' && <Button className='text-button' onClick={() => Taro.navigateTo({ url: `/learning/document/index?docId=${encodeURIComponent(task.result.doc_id)}` })}>查看资料</Button>}
        {task.kind === 'answer' && <Button className='text-button' onClick={() => Taro.navigateTo({ url: `/learning/assistant/index?taskId=${encodeURIComponent(task.task_id)}` })}>查看问答</Button>}
        {task.kind === 'tutor' && task.resource_id && <Button className='text-button' onClick={() => Taro.navigateTo({ url: `/learning/tutor/index?sessionId=${encodeURIComponent(task.resource_id!)}` })}>查看辅导</Button>}
        {task.kind === 'quiz' && <Button className='text-button' onClick={() => Taro.navigateTo({ url: `/pages/quiz/index?taskId=${encodeURIComponent(task.task_id)}` })}>查看练习</Button>}
        {task.kind === 'image' && task.resource_id && <Button className='text-button' onClick={() => Taro.navigateTo({ url: `/pages/quiz/index?quizId=${encodeURIComponent(task.resource_id!)}` })}>查看配图练习</Button>}
        {task.kind === 'grade' && task.resource_id && <Button className='text-button' onClick={() => Taro.navigateTo({ url: task.result?.card_id ? '/learning/review/index' : `/pages/quiz/index?quizId=${encodeURIComponent(task.resource_id!)}` })}>查看评阅</Button>}
        {task.kind === 'report' && task.resource_id && <Button className='text-button' onClick={() => Taro.navigateTo({ url: `/pages/report/index?quizId=${encodeURIComponent(task.resource_id!)}&taskId=${encodeURIComponent(task.task_id)}` })}>查看报告</Button>}
      </View>
      {selected === task.task_id && <View className='task-trace'><Text className='tiny-label'>追踪编号 {task.trace.trace_id}</Text><Text className='muted'>外部调用 {task.trace.model_calls} 次 · 已记录 {task.trace.tokens} tokens{task.trace.unmetered_calls ? ` · ${task.trace.unmetered_calls} 次未返回用量` : ''}</Text>
        {task.trace.nodes.map((node, index) => <View className='trace-row' key={index}><Text>{phase(node.stage)}</Text><Text className='muted'>{Math.round(node.duration_ms)} ms</Text></View>)}
      </View>}
    </View>)}
  </StudioShell>
}
