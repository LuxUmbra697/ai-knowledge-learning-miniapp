import { useRef, useState } from 'react'
import { View, Text, Button, Picker } from '@tarojs/components'
import Taro, { useDidShow, useDidHide } from '@tarojs/taro'
import { StudioShell, Notice, Empty, navigate } from '../../components/StudioShell'
import { Icon } from '../../components/Icon'
import { PollControl } from '../../services/polling'
import { ApiError, getCachedUser, getLearningSummary, getReviewCards, getReviewResult, submitReview, updateReviewCard, waitForLogin, getToken, LearningSummary, ReviewCard, ReviewResult } from '../../services/api'

const modes = [['due', '到期复习'], ['wrong', '错题本'], ['favorites', '收藏'], ['progress', '掌握概况']]
const causes = ['尚未确认', '概念混淆', '前置知识不足', '粗心', '推理缺失']
const causeKeys = [null, 'concept_confusion', 'missing_prerequisite', 'careless', 'reasoning_gap']
const dateText = (value: string) => { const date = new Date(value); return `${date.getMonth() + 1}月${date.getDate()}日 ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}` }

export default function ReviewPage() {
  const [mode, setMode] = useState('due'), [summary, setSummary] = useState<LearningSummary | null>(null)
  const [items, setItems] = useState<ReviewCard[]>([]), [active, setActive] = useState<ReviewCard | null>(null)
  const [result, setResult] = useState<ReviewResult | null>(null), [selected, setSelected] = useState<string[]>([])
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true)
  const live = useRef(true), lock = useRef(false), control = useRef<PollControl>()
  const key = () => `ai-learn:v1:review:${getCachedUser()?.id}`
  const accept = (value: ReviewResult, submittedVersion: number) => {
    Taro.setStorageSync(key(), { cardId: value.card_id, version: submittedVersion })
    if (live.current) { setResult(value); setActive(null); setSelected([]) }
  }
  const load = async (tab = mode) => {
    control.current?.cancel(); const current = new PollControl(); control.current = current
    setLoading(true)
    try {
      await waitForLogin()
      if (!getToken()) { navigate('/pages/login/index'); return }
      const state = await getLearningSummary(current)
      const list = await getReviewCards(tab === 'progress' ? 'all' : tab, current)
      if (!live.current || current.cancelled) return
      setSummary(state); setItems(list.items); setError('')
      const saved = Taro.getStorageSync(key())
      if (saved && /^card_[a-f0-9]{32}$/.test(saved.cardId) && Number.isSafeInteger(saved.version) && saved.version >= 1) {
        const restored = Array.isArray(saved.answers) ? await submitReview(saved.cardId, saved.version, saved.answers, current) : await getReviewResult(saved.cardId, saved.version, current)
        accept(restored, saved.version)
      }
    } catch (reason) {
      if (reason instanceof ApiError && [404, 409, 422].includes(reason.statusCode)) Taro.removeStorageSync(key())
      if (live.current && !current.cancelled) setError(reason instanceof Error ? reason.message : '复习记录读取失败')
    } finally { if (live.current && !current.cancelled) setLoading(false) }
  }
  useDidShow(() => { live.current = true; lock.current = false; setBusy(false); load() })
  useDidHide(() => { live.current = false; control.current?.cancel() })
  const back = (tab = mode) => { Taro.removeStorageSync(key()); setResult(null); setActive(null); setSelected([]); setMode(tab); load(tab) }
  const choose = (answer: string) => {
    if (!active || busy) return
    setSelected(old => active.question.type === 'multiple' ? old.includes(answer) ? old.filter(x => x !== answer) : [...old, answer] : [answer])
  }
  const submit = async () => {
    if (!active || !selected.length || lock.current) return
    lock.current = true; setBusy(true); setError('')
    Taro.setStorageSync(key(), { cardId: active.card_id, version: active.version, answers: selected })
    const current = new PollControl(); control.current = current
    try { accept(await submitReview(active.card_id, active.version, selected, current), active.version) }
    catch (reason) { if (live.current && !current.cancelled) setError(reason instanceof Error ? reason.message : '提交失败，请重试') }
    finally { lock.current = false; if (live.current) setBusy(false) }
  }
  const change = async (card: ReviewCard, settings: { favorite?: boolean; diagnosis?: string | null }) => {
    try { await updateReviewCard(card.card_id, settings); if (live.current) setItems(old => old.map(item => item.card_id === card.card_id ? { ...item, ...settings } : item)) }
    catch (reason) { if (live.current) setError(reason instanceof Error ? reason.message : '保存失败') }
  }
  const question = result?.question || active?.question
  return <StudioShell active='home' title='复习与掌握' subtitle='把一次理解，留到更远的日子。' focus={!!question}>
    {error && <Notice message={error} retry={() => load()} />}
    {question ? <View className='practice-surface review-practice'>
      <Button className='text-button' onClick={() => back()}>返回复习队列</Button>
      <Text className='question-stem'>{question.stem}</Text>
      <Text className='muted'>{question.type === 'multiple' ? '多选题' : question.type === 'judge' ? '判断题' : '单选题'}</Text>
      <View className='answer-options'>{question.options.map(option => <Button key={option.key} className={`answer-option ${(result?.record.selected_answers || selected).includes(option.key) ? 'selected' : ''} ${result && question.answer?.includes(option.key) ? 'correct' : ''}`} onClick={() => choose(option.key)}><Text className='option-key'>{option.key}</Text><Text className='option-text'>{option.text}</Text></Button>)}</View>
      {!result && <Button className='primary-button' disabled={!selected.length || busy} onClick={submit}>{busy ? '正在提交' : '完成本次复习'}</Button>}
      {result && <View className='answer-explanation'><Text className='section-title'>{result.record.is_correct ? '这次记住了' : '再巩固一次'}</Text><Text>参考答案：{question.answer?.join('、')}</Text><Text>{question.explanation}</Text><Text className='next-review'>下次复习：{dateText(result.due_at)}</Text><Text className='muted'>累计 {result.knowledge.observation_count} 次作答 · 默认参数掌握估计 {Math.round(result.knowledge.mastery * 100)}%</Text><Button className='text-button' onClick={() => Taro.navigateTo({ url: `/pages/quiz/index?quizId=${result.quiz_id}` })}>查看原练习与证据<Icon name='book' size={16} /></Button></View>}
    </View> : <>
      {summary && <View className='stats-row'><View className='stat'><Text className='muted'>到期题目</Text><Text className='stat-number'>{summary.due_count}</Text></View><View className='stat'><Text className='muted'>今日已复习</Text><Text className='stat-number'>{summary.today_reviews}</Text></View><View className='stat'><Text className='muted'>本轮建议</Text><Text className='stat-number'>{summary.recommended_count}</Text></View></View>}
      <View className='review-tabs'>{modes.map(([value, label]) => <Button key={value} className={`text-button ${mode === value ? 'active' : ''}`} onClick={() => back(value)}>{label}</Button>)}</View>
      {loading && <Text className='muted'>正在读取学习记录</Text>}
      {!loading && mode !== 'progress' && !items.length && <Empty title={mode === 'due' ? '目前没有到期复习' : mode === 'wrong' ? '还没有错题记录' : '还没有收藏'} text='每次练习都会留下真实的作答记录。' />}
      {mode !== 'progress' && items.map(card => <View className='review-row' key={card.card_id}>
        <View className='section-heading'><Text className='tag'>{card.label}</Text><Button className='text-button' onClick={() => change(card, { favorite: !card.favorite })}><Icon name='book' size={16} />{card.favorite ? '取消收藏' : '收藏'}</Button></View>
        <Text className='row-title'>{card.question.stem}</Text><Text className='muted'>复习时间 {dateText(card.due_at)} · 累计答错 {card.wrong_count} 次</Text>
        <View className='review-actions'>{new Date(card.due_at) <= new Date() ? <Button className='primary-button' onClick={() => { Taro.removeStorageSync(key()); setActive(card); setSelected([]); setError('') }}><Icon name='review' size={16} />开始复习</Button> : <Button className='secondary-button' onClick={() => Taro.navigateTo({ url: `/pages/quiz/index?quizId=${card.quiz_id}` })}>原练习解析</Button>}
          {card.wrong_count > 0 && <Picker mode='selector' range={causes} value={Math.max(0, causeKeys.indexOf(card.diagnosis))} onChange={event => change(card, { diagnosis: causeKeys[Number(event.detail.value)] })}><View className='diagnosis-picker'>错因：{causes[Math.max(0, causeKeys.indexOf(card.diagnosis))]}<Text className='muted'>{card.diagnosis ? ' · 我的确认' : ''}</Text></View></Picker>}
        </View>
      </View>)}
      {mode === 'progress' && summary && <View className='learning-progress'><Text className='section-title'>近两周学习记录</Text><View className='learning-trend'>{summary.trend.map(day => <View className='trend-day' key={day.day}><Text>{day.count}</Text><View className='trend-track'><View className='trend-bar' style={{ height: `${day.count / Math.max(1, ...summary.trend.map(item => item.count)) * 100}%` }} /></View><Text className='tiny-label'>{day.day.slice(5)}</Text></View>)}</View>{summary.trend_truncated && <Notice message='近两周记录超过图表上限，目前显示前 5000 条。' />}
        <Text className='section-title'>知识点掌握估计</Text><Text className='muted'>默认 BKT 参数 · 不是考试得分 · 未进行个人参数训练</Text>
        {!summary.concepts.length && <Empty title='等待第一条作答记录' text='暂无掌握度估计。' />}
        {summary.concepts.map(item => <View className='concept-row' key={item.concept_id}><View className='section-heading'><Text className='row-title'>{item.label}</Text><Text>{Math.round(item.mastery * 100)}%</Text></View><View className='mastery-track'><View style={{ width: `${item.mastery * 100}%` }} /></View><Text className='muted'>答对 {item.correct_count} / {item.attempts} 次 · {item.attempts < 3 ? '记录较少，继续积累' : '重复题目可能相关，估计仍有不确定性'}</Text><Text className='tiny-label'>标签来源：模型{item.mapping_confidence.startsWith('quote') ? ' · 已关联原文引用' : ''} · 未经人工映射审核</Text></View>)}
      </View>}
    </>}
  </StudioShell>
}
