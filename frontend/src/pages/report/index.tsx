import { useState, useRef } from 'react'
import { View, Text, Button } from '@tarojs/components'
import Taro, { useRouter, useDidShow, useDidHide } from '@tarojs/taro'
import { getQuizDetail, generateReportAsync, getLearningTask, cancelLearningTask, getCachedUser, waitForLogin, getToken, QuizDetailResponse, ReportData, LearningTask } from '../../services/api'
import { StudioShell, Notice, navigate } from '../../components/StudioShell'
import { NotebookDialog } from '../../components/NotebookDialog'
import { PollControl, pollUntil } from '../../services/polling'
import { taskPhase } from '../../services/taskDisplay'
import { restorableReport, reportTaskMatches } from '../../services/reportSession'

export default function ReportPage() {
  const router = useRouter()
  const quizId = router.params.quizId || ''
  const [quiz, setQuiz] = useState<QuizDetailResponse | null>(null), [report, setReport] = useState<ReportData | null>(null)
  const [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const [notebookQuestion, setNotebookQuestion] = useState('')
  const [task, setTask] = useState<LearningTask | null>(null)
  const lock = useRef(false), live = useRef(true), control = useRef<PollControl>()
  const storageKey = () => `ai-learn:v1:report:${getCachedUser()?.id}:${quizId}`
  const runTask = async (pending: { key: string; taskId?: string }) => {
    if (lock.current) return
    lock.current = true; setBusy(true); setError('')
    const current = new PollControl(); control.current = current
    const key = storageKey()
    Taro.setStorageSync(key, pending)
    try {
      if (!pending.taskId) {
        const created = await generateReportAsync(quizId, pending.key, current)
        pending = { ...pending, taskId: created.task_id }
        Taro.setStorageSync(key, pending)
      }
      const result = await pollUntil(() => getLearningTask(pending.taskId!, current), update => {
        if (!reportTaskMatches(update, quizId)) {
          Taro.removeStorageSync(key)
          throw new Error('任务不属于这份学习报告，请从任务记录重新进入')
        }
        if (live.current) setTask(update)
        if (update.status === 'failed' || update.status === 'cancelled') {
          Taro.removeStorageSync(key)
          throw new Error(update.error_message || '报告任务已取消，作答记录仍然保留')
        }
        return update.status === 'completed'
      }, { control: current, intervalMs: 2000, maxAttempts: 150 })
      if (live.current) setReport(result.result)
      Taro.removeStorageSync(key)
    } catch (reason) { if (live.current && !current.cancelled) setError(reason instanceof Error ? reason.message : '报告任务读取失败') }
    finally { if (control.current === current) { lock.current = false; if (live.current) setBusy(false) } }
  }
  const load = async () => {
    await waitForLogin()
    if (!getToken()) { navigate('/pages/login/index'); return }
    try {
      const result = await getQuizDetail(quizId)
      if (!live.current) return
      setQuiz(result); setReport(result.report || null); setError('')
      const pending = restorableReport(router.params.taskId, Taro.getStorageSync(storageKey()))
      if (!result.report && pending) await runTask(pending)
      if (result.report) Taro.removeStorageSync(storageKey())
    } catch (reason) { if (live.current) setError(reason instanceof Error ? reason.message : '读取报告失败') }
  }
  useDidShow(() => { live.current = true; load() })
  useDidHide(() => { live.current = false; control.current?.cancel(); control.current = undefined; lock.current = false })
  const records = quiz?.answer_records || [], correct = records.filter(r => r.is_correct).length
  const complete = !!quiz?.questions.length && records.length === quiz.questions.length
  const generate = async () => {
    if (lock.current || !quiz || !complete) return
    const pending = restorableReport(undefined, Taro.getStorageSync(storageKey()))
    await runTask(pending || { key: `report_${Date.now()}_${Math.random().toString(36).slice(2)}` })
  }
  const cancel = async () => {
    if (!task || !busy) return
    const confirmed = await Taro.showModal({ title: '取消报告', content: '作答记录不会删除。已经开始的模型调用可能仍产生费用。' })
    if (!confirmed.confirm) return
    try { await cancelLearningTask(task.task_id) }
    catch (reason) { if (live.current) setError(reason instanceof Error ? reason.message : '取消失败，请稍后重试') }
  }
  return <StudioShell title='这一程的学习收获' subtitle={quiz?.title || '学习报告'} focus={busy}>
    {notebookQuestion && <NotebookDialog target={{ quizId, questionId: notebookQuestion }} onClose={() => setNotebookQuestion('')} />}
    {error && <Notice message={error} retry={load} />}
    {!quiz && !error && <Text className='muted'>正在读取作答记录</Text>}
    {quiz && <>
      <View className='stats-row'><View className='stat'><Text className='muted'>已提交</Text><Text className='stat-number'>{records.length}/{quiz.questions.length}</Text></View><View className='stat'><Text className='muted'>答对题数</Text><Text className='stat-number'>{correct}</Text></View><View className='stat'><Text className='muted'>本次正确率</Text><Text className='stat-number'>{records.length ? `${Math.round(correct / records.length * 100)}%` : '暂无'}</Text></View></View>
      {!complete && <View className='notice'><Text>练习尚未完成，完成后可生成学习报告。</Text><Button className='text-button' onClick={() => Taro.navigateTo({ url: `/pages/quiz/index?quizId=${quizId}` })}>继续作答</Button></View>}
      {complete && !report && <View className='section-band report-actions'><Button className='primary-button' disabled={busy} onClick={generate}>{busy ? taskPhase(task?.stage || 'queued') : '生成学习报告'}</Button>{busy && task && <Button className='text-button' onClick={cancel}>取消报告</Button>}</View>}
      {task && <View className='report-task'><Text className='muted'>任务：{taskPhase(task.stage)} · 外部调用 {task.trace.model_calls} 次</Text><Button className='text-button' onClick={() => Taro.navigateTo({ url: '/learning/tasks/index' })}>查看执行记录</Button></View>}
      {report && <><Text className='section-title'>本次总结</Text><View className='report-list'>{report.three_line_summary.map((line, i) => <Text key={i}>{line}</Text>)}</View><Text className='section-title'>需要巩固的知识点</Text><View className='report-list'>{report.weak_points.length ? report.weak_points.map((line, i) => <Text key={i}>{line}</Text>) : <Text className='muted'>本次练习未发现错误，后续复习仍有助于保持记忆。</Text>}</View><Text className='section-title'>下一步建议</Text><View className='report-list'>{report.advice.map((line, i) => <Text key={i}>{line}</Text>)}</View></>}
      <Text className='section-title'>作答与解析</Text>{quiz.questions.map((q, i) => { const record = records.find(r => r.question_id === q.id); return <View className='report-question' key={q.id}><Text className='row-title'>{i + 1}. {q.stem}</Text><Text className='muted'>{record ? `你的选择：${record.selected_answers.join('、')} · ${record.is_correct ? '正确' : '需巩固'}` : '尚未提交'}</Text>{record && <View className='answer-explanation'><Text className='muted'>参考答案：{q.answer?.join('、')}</Text><Text>{q.explanation}</Text></View>}{record && !record.is_correct && <Button className='secondary-button' onClick={() => setNotebookQuestion(q.id)}>加入错题本</Button>}</View> })}
    </>}
    <Button className='secondary-button' onClick={() => navigate('/pages/index/index')}>返回学习首页</Button>
  </StudioShell>
}
