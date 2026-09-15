import { useState, useCallback, useRef } from 'react'
import { View, Text, Textarea, Button } from '@tarojs/components'
import Taro, { useDidShow, useDidHide } from '@tarojs/taro'
import { StudioShell, Notice, Empty, navigate } from '../../components/StudioShell'
import { Icon } from '../../components/Icon'
import { PollControl } from '../../services/polling'
import { getToken, getCachedUser, getUserProfile, getQuizHistory, getKnowledgeDocuments, generateQuizAsync, pollQuizTask, waitForLogin, getLearningSummary, LearningSummary, UserProfile, QuizHistoryItem } from '../../services/api'

export default function HomePage() {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [history, setHistory] = useState<QuizHistoryItem[]>([])
  const [documentCount, setDocumentCount] = useState(0)
  const [input, setInput] = useState('')
  const [learning, setLearning] = useState<LearningSummary | null>(null)
  const [error, setError] = useState('')
  const [stage, setStage] = useState('')
  const busy = useRef(false)
  const alive = useRef(true)
  const polling = useRef<PollControl | null>(null)
  const load = useCallback(async () => {
    alive.current = true
    await waitForLogin()
    if (!getToken()) { navigate('/pages/login/index'); return }
    try {
      const [user, quizzes, documents, state] = await Promise.all([getUserProfile(), getQuizHistory(1, 4), getKnowledgeDocuments(), getLearningSummary()])
      if (alive.current) { setProfile(user); setHistory(quizzes.items); setDocumentCount(documents.items.length); setLearning(state); setError('') }
    } catch (reason) { if (alive.current) setError(reason instanceof Error ? reason.message : '加载失败') }
  }, [])
  useDidShow(load)
  useDidHide(() => { alive.current = false; polling.current?.cancel() })
  const generate = async () => {
    if (busy.current || !input.trim()) return
    busy.current = true; setError(''); setStage('正在创建练习')
    try {
      const { task_id } = await generateQuizAsync(input.trim())
      if (!alive.current) return
      polling.current = new PollControl()
      const quiz = await pollQuizTask(task_id, status => { if (alive.current) setStage(status === 'pending' ? '等待处理' : '正在生成练习') }, 3000, 100, polling.current)
      if (alive.current) Taro.navigateTo({ url: `/pages/quiz/index?quizId=${quiz.quiz_id}` })
    } catch (reason) { if (alive.current) setError(reason instanceof Error ? reason.message : '生成失败，请重试') }
    finally { busy.current = false; if (alive.current) setStage('') }
  }
  return <StudioShell active='home' title='今天，也向前一小步' subtitle={`${profile?.nickname || getCachedUser()?.nickname || '同学'}，欢迎回到你的学习空间。`}>
    {error && <Notice message={error} retry={load} />}
    <View className='today-review section-heading'><View><Text className='section-title'>今日复习</Text><Text className='muted'>{learning ? `${learning.due_count} 道到期 · 今日已复习 ${learning.today_reviews} 道` : '正在读取复习计划'}</Text></View><Button className='secondary-button' onClick={() => Taro.navigateTo({ url: '/learning/review/index' })}><Icon name='review' size={17} />复习与掌握</Button></View>
    <View className='welcome-band'><View><Text className='tiny-label'>MY LEARNING NOTEBOOK</Text><Text className='welcome-title'>从一页知识，开始一次发现</Text><Text className='muted'>你的材料、练习与学习记录，都在这里。</Text></View><Button className='primary-button' onClick={() => navigate('/pages/knowledge/index')}><Icon name='upload' size={18} />添加学习材料</Button></View>
    <View className='stats-row'><View className='stat'><Text className='muted'>我的知识文档</Text><Text className='stat-number'>{documentCount}</Text><Text className='tiny-label'>篇学习材料</Text></View><View className='stat'><Text className='muted'>累计练习</Text><Text className='stat-number'>{profile?.quiz_count || 0}</Text><Text className='tiny-label'>次探索与尝试</Text></View><View className='stat'><Text className='muted'>已完成正确率</Text><Text className='stat-number'>{profile?.quiz_count ? `${profile.average_accuracy}%` : '暂无'}</Text><Text className='tiny-label'>{profile?.total_xp || 0} 学习经验</Text></View></View>
    <View className='dashboard-grid'><View className='section-band'><View className='section-heading'><Text className='section-title'>自由练习</Text><Text className='tag'>主题练习</Text></View><Textarea className='studio-textarea' placeholder='今天想学习什么？例如：Python 列表与字典的区别' value={input} maxlength={2000} onInput={e => setInput(e.detail.value)} /><View className='section-heading' style={{ marginTop: '14px' }}><Text className='muted'>{input.length}/2000</Text><Button className='primary-button' disabled={!input.trim() || !!stage} onClick={generate}><Icon name='sparkle' size={17} />{stage || '生成练习'}</Button></View></View>
      <View className='section-band'><View className='section-heading'><Text className='section-title'>最近的学习足迹</Text><Button className='text-button' onClick={() => navigate('/pages/profile/index')}>全部记录<Icon name='arrow' size={16} /></Button></View>{history.length ? history.map(item => <View className='history-row' key={item.quiz_id} onClick={() => Taro.navigateTo({ url: `/pages/report/index?quizId=${item.quiz_id}` })}><View className='row-copy'><Text className='row-title'>{item.title}</Text><Text className='muted'>{item.created_at}</Text></View><Text className='score-badge'>{item.accuracy}%</Text></View>) : <Empty title='第一段足迹，等你留下' text='添加材料或完成一次主题练习，学习记录就会出现在这里。' />}</View>
    </View>
  </StudioShell>
}
