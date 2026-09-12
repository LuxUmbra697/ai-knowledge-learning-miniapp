import { useEffect, useState, useRef } from 'react'
import { View, Text, Button } from '@tarojs/components'
import Taro, { useRouter } from '@tarojs/taro'
import { getQuizDetail, generateReport, QuizDetailResponse, ReportData } from '../../services/api'
import { StudioShell, Notice, navigate } from '../../components/StudioShell'

export default function ReportPage() {
  const router = useRouter()
  const quizId = router.params.quizId || ''
  const [quiz, setQuiz] = useState<QuizDetailResponse | null>(null), [report, setReport] = useState<ReportData | null>(null)
  const [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const lock = useRef(false)
  const load = async () => {
    try { const result = await getQuizDetail(quizId); setQuiz(result); setReport(result.report || null); setError('') }
    catch (reason) { setError(reason instanceof Error ? reason.message : '读取报告失败') }
  }
  useEffect(() => { load() }, [quizId])
  const records = quiz?.answer_records || [], correct = records.filter(r => r.is_correct).length
  const complete = !!quiz?.questions.length && records.length === quiz.questions.length
  const generate = async () => {
    if (lock.current || !quiz || !complete) return
    lock.current = true; setBusy(true); setError('')
    try { const result = await generateReport({ quiz_id: quizId, topic: quiz.title, questions: quiz.questions, answer_records: records }); setReport(result) }
    catch (reason) { setError(reason instanceof Error ? reason.message : '报告生成失败') }
    finally { lock.current = false; setBusy(false) }
  }
  return <StudioShell title='这一程的学习收获' subtitle={quiz?.title || '学习报告'} focus={busy}>
    {error && <Notice message={error} retry={load} />}
    {!quiz && !error && <Text className='muted'>正在读取作答记录</Text>}
    {quiz && <>
      <View className='stats-row'><View className='stat'><Text className='muted'>已提交</Text><Text className='stat-number'>{records.length}/{quiz.questions.length}</Text></View><View className='stat'><Text className='muted'>答对题数</Text><Text className='stat-number'>{correct}</Text></View><View className='stat'><Text className='muted'>本次正确率</Text><Text className='stat-number'>{records.length ? `${Math.round(correct / records.length * 100)}%` : '暂无'}</Text></View></View>
      {!complete && <View className='notice'><Text>练习尚未完成，完成后可生成学习报告。</Text><Button className='text-button' onClick={() => Taro.navigateTo({ url: `/pages/quiz/index?quizId=${quizId}` })}>继续作答</Button></View>}
      {complete && !report && <View className='section-band'><Button className='primary-button' disabled={busy} onClick={generate}>{busy ? '正在生成学习报告' : '生成学习报告'}</Button></View>}
      {report && <><Text className='section-title'>本次总结</Text><View className='report-list'>{report.three_line_summary.map((line, i) => <Text key={i}>{line}</Text>)}</View><Text className='section-title'>需要巩固的知识点</Text><View className='report-list'>{report.weak_points.length ? report.weak_points.map((line, i) => <Text key={i}>{line}</Text>) : <Text className='muted'>本次练习未发现错误，后续复习仍有助于保持记忆。</Text>}</View><Text className='section-title'>下一步建议</Text><View className='report-list'>{report.advice.map((line, i) => <Text key={i}>{line}</Text>)}</View></>}
      <Text className='section-title'>作答与解析</Text>{quiz.questions.map((q, i) => { const record = records.find(r => r.question_id === q.id); return <View className='report-question' key={q.id}><Text className='row-title'>{i + 1}. {q.stem}</Text><Text className='muted'>{record ? `你的选择：${record.selected_answers.join('、')} · ${record.is_correct ? '正确' : '需巩固'}` : '尚未提交'}</Text>{record && <View className='answer-explanation'><Text className='muted'>参考答案：{q.answer?.join('、')}</Text><Text>{q.explanation}</Text></View>}</View> })}
    </>}
    <Button className='secondary-button' onClick={() => navigate('/pages/index/index')}>返回学习首页</Button>
  </StudioShell>
}
