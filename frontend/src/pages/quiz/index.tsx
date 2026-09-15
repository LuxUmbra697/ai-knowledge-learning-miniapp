import { useRef, useState } from 'react'
import { View, Text, Button } from '@tarojs/components'
import Taro, { useRouter, useDidShow, useDidHide } from '@tarojs/taro'
import { getQuizDetail, submitAnswer, QuizDetailResponse, AnswerRecord, getCachedUser, getLearningTask, cancelLearningTask, LearningTask, waitForLogin, getToken } from '../../services/api'
import { StudioShell, Notice, navigate } from '../../components/StudioShell'
import { Icon } from '../../components/Icon'
import { NotebookDialog } from '../../components/NotebookDialog'
import { QuizSources } from '../../components/QuizSources'
import { QuestionMedia } from '../../components/QuestionMedia'
import { PollControl, pollUntil } from '../../services/polling'
import { taskPhase } from '../../services/taskDisplay'
import { quizTaskResult } from '../../services/quizSession'
import { TextAnswer, GradingFeedback, answerComplete } from '../../components/TextAnswer'
import { questionLabels } from '../../services/quizBlueprint'
import { pendingWritten, submitWritten } from '../../services/writtenGrade'

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
  const [notebook, setNotebook] = useState(false)
  const [gradingTask, setGradingTask] = useState<LearningTask | null>(null)
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
      const linked = result.questions.findIndex(q => q.id === router.params.questionId)
      const position = linked >= 0 ? linked : next < 0 ? 0 : next
      const draft = Taro.getStorageSync(draftKeyFor(targetId))
      setQuiz(result); setRecords(attempts); setIndex(position)
      const target = result.questions[position]
      setSelected(draft?.questionId === target?.id && Array.isArray(draft.selected) ? draft.selected.filter((key: string) => typeof key === 'string' && (['fill', 'written'].includes(target.type) || target.options.some(o => o.key === key))) : [])
      setError('')
      const pending = target?.type === 'written' && !attempts.some(item => item.question_id === target.id) ? pendingWritten(targetId, target.id) : null
      if (pending) {
        setBusy(true); lock.current = true; setSelected(pending.answers)
        try {
          const reviewed = await submitWritten(targetId, target.id, pending.answers, pending.duration, current, setGradingTask)
          if (live.current && !current.cancelled) {
            setRecords(previous => [...previous.filter(item => item.question_id !== target.id), reviewed.record])
            setQuiz(previous => previous && ({ ...previous, questions: previous.questions.map(q => q.id === target.id ? reviewed.question : q) }))
          }
        } finally { lock.current = false; if (live.current) setBusy(false) }
      }
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
    if (lock.current || !question || !answerComplete(question, selected) || record) return
    lock.current = true; setBusy(true); setError('')
    try {
      const current = new PollControl(); control.current = current
      const duration = Math.min(86400000, Date.now() - start.current)
      const result = question.type === 'written' ? await submitWritten(quizId, question.id, selected, duration, current, setGradingTask) : await submitAnswer(quizId, question.id, selected, duration)
      if (!live.current || current.cancelled) return
      setRecords(previous => [...previous.filter(r => r.question_id !== question.id), result.record])
      setQuiz(previous => previous && ({ ...previous, questions: previous.questions.map(q => q.id === question.id ? result.question : q) }))
      Taro.removeStorageSync(draftKey)
    } catch (reason) { setError(reason instanceof Error ? reason.message : '提交失败，请重试') }
    finally { lock.current = false; setBusy(false) }
  }
  const move = (next: number) => { if (busy) return; setIndex(next); setSelected([]); setGradingTask(null); start.current = Date.now() }
  return <StudioShell title={quiz?.title || '知识练习'} subtitle='先独立思考，再与解析对照。' focus>
    {notebook && question && <NotebookDialog target={{ quizId, questionId: question.id }} onClose={() => setNotebook(false)} />}
    <View className='practice-surface'>
      {error && <Notice message={error} retry={load} />}
      {!question && !error && <Text className='muted'>{task ? taskPhase(task.stage) : '正在读取练习'}</Text>}
      {task && !quiz && <View className='report-task'><Text className='muted'>外部调用 {task.trace.model_calls} 次</Text>{!['completed', 'failed', 'cancelled'].includes(task.status) && <Button className='text-button' onClick={cancel}>取消练习</Button>}<Button className='text-button' onClick={() => Taro.navigateTo({ url: '/learning/tasks/index' })}>查看执行记录</Button></View>}
      {question && <>
        <QuizSources source={quiz?.source_context} />
        <View className='section-heading'><Text className='tag'>{questionLabels[question.type]}</Text><Text className='muted'>第 {index + 1} / {quiz!.questions.length} 题 · 已完成 {records.length} 题</Text></View>
        <View className='practice-progress'><View className='practice-progress-fill' style={{ width: `${records.length / quiz!.questions.length * 100}%` }} /></View>
        <Text className='question-stem'>{question.stem}</Text>
        <QuestionMedia assetId={question.image_asset_id} legacyUrl={question.image_url} revealed={!!record} />
        <View className='answer-options'>{question.options.map(option => <Button key={option.key} className={`answer-option ${(record?.selected_answers || selected).includes(option.key) ? 'selected' : ''} ${record && question.answer?.includes(option.key) ? 'correct' : record && record.selected_answers.includes(option.key) ? 'wrong' : ''}`} onClick={() => choose(option.key)} aria-pressed={(record?.selected_answers || selected).includes(option.key)}><Text className='option-key'>{option.key}</Text><Text className='option-text'>{option.text}</Text></Button>)}</View>
        <TextAnswer question={question} values={record?.selected_answers || selected} disabled={!!record || busy} onChange={values => { setSelected(values); Taro.setStorageSync(draftKey, { questionId: question.id, selected: values }) }} />
        {!record && <Button className='primary-button' disabled={!answerComplete(question, selected) || busy} onClick={submit}>{busy ? gradingTask ? taskPhase(gradingTask.stage) : '正在提交' : '确认答案'}</Button>}
        {busy && gradingTask && <Button className='text-button' onClick={async () => { const result = await Taro.showModal({ title: '取消评阅', content: '已开始的模型调用可能产生费用，取消后不发布结果。' }); if (result.confirm) await cancelLearningTask(gradingTask.task_id) }}>取消评阅</Button>}
        {record && <View className='answer-explanation'><Text className='section-title'>{record.is_correct ? '回答正确' : '再理解一次'}</Text><Text className='muted'>你的选择：{record.selected_answers.join('、')} · 参考答案：{question.answer?.join('、')}</Text><Text>{question.explanation}</Text></View>}
        {record && !record.is_correct && <Button className='secondary-button' onClick={() => setNotebook(true)}><Icon name='book' size={16} />加入错题本</Button>}
        {record && <GradingFeedback record={record} />}
        {record && !!question.citations?.length && <View className='quiz-evidence'><Text className='section-title'>对照原文</Text>{question.citations.map((citation, i) => <View className='quiz-citation' key={`${citation.evidence_id}-${i}`}>
          {citation.status === 'verified' && citation.doc_id && citation.chunk_id ? <><Text className='citation-quote' selectable>{citation.quote}</Text><Button className='text-button citation-link' onClick={() => Taro.navigateTo({ url: `/learning/document/index?docId=${encodeURIComponent(citation.doc_id!)}&chunkId=${encodeURIComponent(citation.chunk_id!)}&revision=${citation.revision}` })}><Icon name='book' size={16} /><Text>{citation.file_name}{citation.page ? ` · 第 ${citation.page} 页` : citation.section ? ` · ${citation.section}` : ''}</Text></Button></> : <Text className='muted'>此引用暂不可用，原材料可能已变更或删除。</Text>}
        </View>)}</View>}
        <View className='practice-navigation'><Button className='secondary-button' disabled={index === 0} onClick={() => move(index - 1)}>上一题</Button>{index + 1 < quiz!.questions.length ? <Button className='secondary-button' onClick={() => move(index + 1)}>下一题<Icon name='arrow' size={16} /></Button> : <Button className='primary-button' disabled={records.length !== quiz!.questions.length} onClick={() => Taro.navigateTo({ url: `/pages/report/index?quizId=${quizId}` })}>查看学习报告</Button>}</View>
      </>}
      <Button className='text-button' onClick={() => navigate('/pages/index/index')}>返回学习首页</Button>
    </View>
  </StudioShell>
}
