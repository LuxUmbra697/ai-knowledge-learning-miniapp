import { useState, useCallback, useRef } from 'react'
import { View, Text, Textarea, Button, Image, Switch } from '@tarojs/components'
import Taro, { useDidShow, useDidHide } from '@tarojs/taro'
import { StudioShell, Notice, Empty, navigate } from '../../components/StudioShell'
import { Icon } from '../../components/Icon'
import { useShareEntry } from '../../services/useShareEntry'
import { QuestionCountsEditor } from '../../components/QuestionCountsEditor'
import { assetUrl } from '../../services/assets'
import { defaultCounts, countQuestions, validCounts } from '../../services/quizBlueprint'
import { restorableTopic, TopicPractice } from '../../services/quizSession'
import { getToken, getCachedUser, getUserProfile, getQuizHistory, getKnowledgeDocuments, generateQuizAsync, getLearningTask, ApiError, waitForLogin, getLearningSummary, LearningSummary, UserProfile, QuizHistoryItem } from '../../services/api'

export default function HomePage() {
  useShareEntry()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [history, setHistory] = useState<QuizHistoryItem[]>([])
  const [documentCount, setDocumentCount] = useState(0)
  const [input, setInput] = useState('')
  const [counts, setCounts] = useState(defaultCounts)
  const [web, setWeb] = useState(false)
  const [illustrated, setIllustrated] = useState(false)
  const [pending, setPending] = useState<TopicPractice | null>(null)
  const [learning, setLearning] = useState<LearningSummary | null>(null)
  const [error, setError] = useState('')
  const [stage, setStage] = useState('')
  const busy = useRef(false)
  const alive = useRef(true)
  const storageKey = () => `ai-learn:v1:topic-practice:${getCachedUser()?.id}`
  const load = useCallback(async () => {
    alive.current = true
    await waitForLogin()
    if (!getToken()) { navigate('/pages/login/index'); return }
    const saved = restorableTopic(Taro.getStorageSync(storageKey()))
    setPending(saved)
    if (saved) { setInput(saved.input); setCounts(saved.counts); setWeb(saved.web); setIllustrated(saved.illustrated) }
    if (!busy.current) setStage('')
    try {
      const [user, quizzes, documents, state] = await Promise.all([getUserProfile(), getQuizHistory(1, 4), getKnowledgeDocuments(), getLearningSummary()])
      if (alive.current) { setProfile(user); setHistory(quizzes.items); setDocumentCount(documents.items.length); setLearning(state); setError('') }
    } catch (reason) { if (alive.current) setError(reason instanceof Error ? reason.message : '加载失败') }
  }, [])
  useDidShow(load)
  useDidHide(() => { alive.current = false })
  const generate = async () => {
    if (busy.current || !input.trim() || !validCounts(counts)) return
    busy.current = true; setError(''); setStage('正在创建练习')
    const key = storageKey()
    try {
      let saved = restorableTopic(Taro.getStorageSync(key)) || { key: `topic_${Date.now()}_${Math.random().toString(36).slice(2)}`, input: input.trim(), counts, web, illustrated }
      Taro.setStorageSync(key, saved); setPending(saved)
      if (!saved.taskId) {
        const { task_id } = await generateQuizAsync(saved.input, countQuestions(saved.counts), undefined, saved.illustrated, saved.key, saved.counts, saved.web)
        saved = { ...saved, taskId: task_id }; Taro.setStorageSync(key, saved); setPending(saved)
      }
      if (!alive.current) return
      Taro.navigateTo({ url: `/pages/quiz/index?taskId=${encodeURIComponent(saved.taskId!)}` })
    } catch (reason) {
      if (reason instanceof ApiError && [400, 404, 409, 422].includes(reason.statusCode)) { Taro.removeStorageSync(key); setPending(null) }
      if (alive.current) setError(reason instanceof Error ? reason.message : '生成失败，请重试')
    }
    finally { busy.current = false; if (alive.current) setStage('') }
  }
  const newPractice = async () => {
    if (busy.current || !pending?.taskId) return
    busy.current = true
    try {
      const task = await getLearningTask(pending.taskId)
      if (!['completed', 'failed', 'cancelled'].includes(task.status)) { setError('上一组仍在处理，请继续查看或取消后再新建。'); return }
      Taro.removeStorageSync(storageKey()); setPending(null); setError('')
    } catch (reason) {
      if (reason instanceof ApiError && reason.statusCode === 404) { Taro.removeStorageSync(storageKey()); setPending(null) }
      else setError(reason instanceof Error ? reason.message : '读取任务失败')
    } finally { busy.current = false }
  }
  return <StudioShell active='home' title='学习手帐' subtitle={`${profile?.nickname || getCachedUser()?.nickname || '同学'}，今天想读些什么？`}>
    {error && <Notice message={error} retry={load} />}
    <View className='study-window'><Image className='study-panorama' src={assetUrl('library-garden.jpg')} mode='aspectFit' /></View>
    <View className='today-review section-heading'><View><Text className='section-title'>今日复习</Text><Text className='muted'>{learning ? `${learning.due_count} 道到期 · 今日已复习 ${learning.today_reviews} 道` : '正在读取复习计划'}</Text></View><Button className='secondary-button' onClick={() => Taro.navigateTo({ url: '/learning/review/index' })}><Icon name='review' size={17} />复习与掌握</Button></View>
    <View className='document-actions'><Button className='text-button' onClick={() => Taro.navigateTo({ url: '/learning/path/index' })}><Icon name='review' size={17} />学习路径与计划</Button></View>
    <View className='welcome-band'><Text className='welcome-title'>我的知识书架</Text><Button className='primary-button' onClick={() => navigate('/pages/knowledge/index')}><Icon name='upload' size={18} />添加学习材料</Button></View>
    <View className='stats-row'><View className='stat'><Text className='muted'>我的知识文档</Text><Text className='stat-number'>{documentCount}</Text><Text className='tiny-label'>篇学习材料</Text></View><View className='stat'><Text className='muted'>累计练习</Text><Text className='stat-number'>{profile?.quiz_count || 0}</Text><Text className='tiny-label'>次探索与尝试</Text></View><View className='stat'><Text className='muted'>已完成正确率</Text><Text className='stat-number'>{profile?.quiz_count ? `${profile.average_accuracy}%` : '暂无'}</Text><Text className='tiny-label'>{profile?.total_xp || 0} 学习经验</Text></View></View>
    <View className='dashboard-grid'><View className='section-band'><View className='section-heading'><Text className='section-title'>自由练习</Text><Text className='tag'>主题练习</Text></View><Textarea className='studio-textarea' placeholder='今天想学习什么？例如：Python 列表与字典的区别' value={input} maxlength={2000} disabled={!!pending || !!stage} onInput={e => setInput(e.detail.value)} /><QuestionCountsEditor value={counts} onChange={setCounts} disabled={!!stage || !!pending} illustrated={illustrated} onIllustratedChange={setIllustrated} />{!validCounts(counts) && <Notice message='题型数量合计须为 1 至 20。' />}<View className='section-heading'><Text>网页参考</Text><Switch checked={web} disabled={!!pending || !!stage} onChange={e => setWeb(e.detail.value)} /></View>{web && <Text className='muted'>本次主题将发送给网页搜索服务。请勿输入私人材料或个人信息。</Text>}<View className='section-heading' style={{ marginTop: '14px' }}><Text className='muted'>{input.length}/2000</Text><Button className='primary-button' disabled={!input.trim() || !!stage || !validCounts(counts)} onClick={generate}><Icon name='sparkle' size={17} />{stage || (pending ? '继续上次练习' : '生成练习')}</Button></View>{pending?.taskId && <Button className='text-button' onClick={newPractice}><Icon name='add' size={16} />新一组练习</Button>}</View>
      <View className='section-band'><View className='section-heading'><Text className='section-title'>最近的学习足迹</Text><Button className='text-button' onClick={() => navigate('/pages/profile/index')}>全部记录<Icon name='arrow' size={16} /></Button></View>{history.length ? history.map(item => <View className='history-row' key={item.quiz_id} onClick={() => Taro.navigateTo({ url: `/pages/report/index?quizId=${item.quiz_id}` })}><View className='row-copy'><Text className='row-title'>{item.title}</Text><Text className='muted'>{item.created_at}</Text></View><Text className='score-badge'>{item.accuracy}%</Text></View>) : <Empty title='第一段足迹，等你留下' text='添加材料或完成一次主题练习，学习记录就会出现在这里。' />}</View>
    </View>
  </StudioShell>
}
