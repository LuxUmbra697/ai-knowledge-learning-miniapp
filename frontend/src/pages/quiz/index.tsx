import { useRef, useState } from 'react'
import { View, Text, Image, Button } from '@tarojs/components'
import Taro, { useRouter, useDidShow, useDidHide } from '@tarojs/taro'
import { getQuizDetail, submitAnswer, QuizDetailResponse, AnswerRecord, getCachedUser, getLearningTask, cancelLearningTask, LearningTask, waitForLogin, getToken } from '../../services/api'
import { StudioShell, Notice, navigate } from '../../components/StudioShell'
import { Icon } from '../../components/Icon'
import { PollControl, pollUntil } from '../../services/polling'
import { taskPhase } from '../../services/taskDisplay'
import { quizTaskResult } from '../../services/quizSession'

export default function QuizPage() {
  const router = useRouter()
  let routeQuizId = router.params.quizId || ''
  try { if (!routeQuizId && router.params.quizData) routeQuizId = JSON.parse(decodeURIComponent(router.params.quizData)).quiz_id || '' } catch { /* Legacy malformed links show a recoverable error. */ }
  const taskId = router.params.taskId || ''
  const [quizId, setQuizId] = useState(routeQuizId), [task, setTask] = useState<LearningTask | null>(null)
  const [quiz, setQuiz] = useState<QuizDetailResponse | null>(null)
  const [index, setIndex] = useState(0), [selected, setSelected] = useState<string[]>([])
  const [records, setRecords] = useState<AnswerRecord[]>([])
  const [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const lock = useRef(false), start = useRef(Date.now())
  const live = useRef(true), control = useRef<PollControl>()
  const draftKeyFor = (id: string) => `ai-learn:v1:draft:${getCachedUser()?.id}:${id}`
  const draftKey = draftKeyFor(quizId)
  const question = quiz?.questions[index], record = records.find(item => item.question_id === question?.id)
  const load = async () => {
    control.current?.cancel(); const current = new PollControl(); control.current = current
    try {
      await waitForLogin()
      if (current.cancelled || !live.current) return
      if (!getToken()) { navigate('/pages/login/index'); return }
      setError('')
      let targetId = routeQuizId
      if (taskId) {
        const done = await pollUntil(() => getLearningTask(taskId, current), update => {
          const target = quizTaskResult(update)
          if (live.current) setTask(update)
          if (update.status === 'failed' || update.status === 'cancelled') throw new Error(update.error_message || '练习任务已取消，未发布新题目')
          return !!target
        }, { control: current, intervalMs: 2000, maxAttempts: 150 })
        targetId = quizTaskResult(done)!
        if (routeQuizId && routeQuizId !== targetId) throw new Error('任务与练习不匹配，请从任务记录重新进入')
      }
      if (!targetId) throw new Error('练习链接不完整，请从学习记录重新进入')
      const result = await getQuizDetail(targetId)
      if (current.cancelled || !live.current) return
      setQuizId(targetId)
      const attempts = result.answer_records || []
      const next = result.questions.findIndex(q => !attempts.some(a => a.question_id === q.id))
      const position = next < 0 ? 0 : next
      const draft = Taro.getStorageSync(draftKeyFor(targetId))
      setQuiz(result); setRecords(attempts); setIndex(position)
      setSelected(draft?.questionId === result.questions[position]?.id && Array.isArray(draft.selected) ? draft.selected.filter((key: string) => result.questions[position].options.some(o => o.key === key)) : [])
      setError('')
    } catch (reason) { if (live.current && !current.cancelled) setError(reason instanceof Error ? reason.message : '读取练习失败') }
  }
  useDidShow(() => { live.current = true; load() })
  useDidHide(() => { live.current = false; control.current?.cancel() })
  const cancel = async () => {
    if (!task) return
    const confirmed = await Taro.showModal({ title: '取消练习', content: '取消后不发布题目。已经开始的模型调用可能仍产生费用。' })
    if (!confirmed.confirm) return
    try { await cancelLearningTask(task.task_id) }
    catch (reason) { if (live.current) setError(reason instanceof Error ? reason.message : '取消失败，请稍后重试') }
  }
  const choose = (key: string) => {
    if (record || busy || !question) return
    const values = question.type === 'multiple' ? selected.includes(key) ? selected.filter(x => x !== key) : [...selected, key] : [key]
    setSelected(values); Taro.setStorageSync(draftKey, { questionId: question.id, selected: values })
  }
  const submit = async () => {
    if (lock.current || !question || !selected.length || record) return
    lock.current = true; setBusy(true); setError('')
    try {
      const result = await submitAnswer(quizId, question.id, selected, Math.min(86400000, Date.now() - start.current))
      setRecords(previous => [...previous.filter(r => r.question_id !== question.id), result.record])
      setQuiz(previous => previous && ({ ...previous, questions: previous.questions.map(q => q.id === question.id ? result.question : q) }))
      Taro.removeStorageSync(draftKey)
    } catch (reason) { setError(reason instanceof Error ? reason.message : '提交失败，请重试') }
    finally { lock.current = false; setBusy(false) }
  }
  const move = (next: number) => { setIndex(next); setSelected([]); start.current = Date.now() }
  return <StudioShell title={quiz?.title || '知识练习'} subtitle='先独立思考，再与解析对照。' focus>
    <View className='practice-surface'>
      {error && <Notice message={error} retry={load} />}
      {!question && !error && <Text className='muted'>{task ? taskPhase(task.stage) : '正在读取练习'}</Text>}
      {task && !quiz && <View className='report-task'><Text className='muted'>外部调用 {task.trace.model_calls} 次</Text>{!['completed', 'failed', 'cancelled'].includes(task.status) && <Button className='text-button' onClick={cancel}>取消练习</Button>}<Button className='text-button' onClick={() => Taro.navigateTo({ url: '/learning/tasks/index' })}>查看执行记录</Button></View>}
      {question && <>
        <View className='section-heading'><Text className='tag'>{({ single: '单选题', multiple: '多选题', judge: '判断题' })[question.type]}</Text><Text className='muted'>第 {index + 1} / {quiz!.questions.length} 题 · 已完成 {records.length} 题</Text></View>
        <View className='practice-progress'><View className='practice-progress-fill' style={{ width: `${records.length / quiz!.questions.length * 100}%` }} /></View>
        <Text className='question-stem'>{question.stem}</Text>
        {question.image_url && /^https:\/\//.test(question.image_url) && <Image className='question-media' src={question.image_url} mode='aspectFit' />}
        <View className='answer-options'>{question.options.map(option => <Button key={option.key} className={`answer-option ${(record?.selected_answers || selected).includes(option.key) ? 'selected' : ''} ${record && question.answer?.includes(option.key) ? 'correct' : record && record.selected_answers.includes(option.key) ? 'wrong' : ''}`} onClick={() => choose(option.key)} aria-pressed={(record?.selected_answers || selected).includes(option.key)}><Text className='option-key'>{option.key}</Text><Text className='option-text'>{option.text}</Text></Button>)}</View>
        {!record && <Button className='primary-button' disabled={!selected.length || busy} onClick={submit}>{busy ? '正在提交' : '确认答案'}</Button>}
        {record && <View className='answer-explanation'><Text className='section-title'>{record.is_correct ? '回答正确' : '再理解一次'}</Text><Text className='muted'>你的选择：{record.selected_answers.join('、')} · 参考答案：{question.answer?.join('、')}</Text><Text>{question.explanation}</Text></View>}
        <View className='practice-navigation'><Button className='secondary-button' disabled={index === 0} onClick={() => move(index - 1)}>上一题</Button>{index + 1 < quiz!.questions.length ? <Button className='secondary-button' onClick={() => move(index + 1)}>下一题<Icon name='arrow' size={16} /></Button> : <Button className='primary-button' disabled={records.length !== quiz!.questions.length} onClick={() => Taro.navigateTo({ url: `/pages/report/index?quizId=${quizId}` })}>查看学习报告</Button>}</View>
      </>}
      <Button className='text-button' onClick={() => navigate('/pages/index/index')}>返回学习首页</Button>
    </View>
  </StudioShell>
}
