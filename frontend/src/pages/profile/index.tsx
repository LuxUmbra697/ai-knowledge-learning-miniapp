import { useState, useRef } from 'react'
import { View, Text, Button, Input } from '@tarojs/components'
import Taro, { useDidShow, useDidHide } from '@tarojs/taro'
import { getUserProfile, getQuizHistory, updateUserProfile, setCachedUser, clearToken, getToken, waitForLogin, UserProfile, QuizHistoryItem } from '../../services/api'
import { StudioShell, Notice, Empty, navigate } from '../../components/StudioShell'
import { Icon } from '../../components/Icon'
import { useShareEntry } from '../../services/useShareEntry'

export default function ProfilePage() {
  useShareEntry()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [history, setHistory] = useState<QuizHistoryItem[]>([])
  const [nickname, setNickname] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const live = useRef(true), lock = useRef(false)
  const load = async (nextPage = 1) => {
    if (lock.current) return
    await waitForLogin()
    if (!getToken()) { navigate('/pages/login/index'); return }
    lock.current = true; setLoading(true)
    try {
      const user = await getUserProfile(), result = await getQuizHistory(nextPage)
      if (!live.current) return
      setProfile(user); setCachedUser(user); setNickname(user.nickname)
      setHistory(previous => nextPage === 1 ? result.items : [...previous, ...result.items])
      setPage(nextPage); setTotal(result.total); setError('')
    } catch (reason) { if (live.current) setError(reason instanceof Error ? reason.message : '加载失败') }
    finally { lock.current = false; if (live.current) setLoading(false) }
  }
  useDidShow(() => { live.current = true; load() })
  useDidHide(() => { live.current = false })
  const save = async () => {
    if (lock.current || !nickname.trim()) return
    lock.current = true; setLoading(true)
    try { await updateUserProfile({ nickname: nickname.trim() }); setError(''); Taro.showToast({ title: '昵称已保存', icon: 'success' }) }
    catch (reason) { setError(reason instanceof Error ? reason.message : '保存失败') }
    finally { lock.current = false; setLoading(false) }
    await load()
  }
  return <StudioShell active='profile' title='我的学习档案' subtitle='收藏每一段认真学习的时光。'>
    {error && <Notice message={error} retry={() => load()} />}
    <Button className='text-button' onClick={() => Taro.navigateTo({ url: '/learning/security/index' })}><Icon name='user' size={18} />账号安全与微信绑定</Button>
    {process.env.TARO_ENV === 'weapp' && <Button className='text-button wechat-share' openType='share'><Icon name='share' size={18} />邀请朋友来学园</Button>}
    <View className='profile-form'><Text className='field-label'>学园昵称</Text><Input className='studio-input' value={nickname} maxlength={40} onInput={e => setNickname(e.detail.value)} /><View className='document-actions'><Button className='secondary-button' disabled={loading || !nickname.trim()} onClick={save}>保存昵称</Button><Button className='text-button' onClick={() => { clearToken(); navigate('/pages/login/index') }}><Icon name='logout' size={16} />退出登录</Button></View></View>
    <View className='stats-row'><View className='stat'><Text className='muted'>已完成练习</Text><Text className='stat-number'>{profile?.quiz_count ?? 0}</Text></View><View className='stat'><Text className='muted'>答对题数</Text><Text className='stat-number'>{profile?.correct_count ?? 0}</Text></View><View className='stat'><Text className='muted'>学习经验</Text><Text className='stat-number'>{profile?.total_xp ?? 0}</Text></View></View>
    <View className='section-heading'><Text className='section-title'>学习记录</Text><Button className='text-button' onClick={() => Taro.navigateTo({ url: '/learning/tasks/index' })}><Icon name='clock' size={16} />任务记录</Button></View>
    <Text className='muted'>共 {total} 次已完成练习</Text>
    {!history.length && <Empty title={loading ? '正在读取学习记录' : '还没有完成的练习'} text='完成练习后，可以在这里回看作答与报告。' />}
    {history.map(item => <View className='history-row' key={item.quiz_id} onClick={() => Taro.navigateTo({ url: `/pages/report/index?quizId=${item.quiz_id}` })}><View className='row-copy'><Text className='row-title'>{item.title}</Text><Text className='muted'>{item.question_count} 题 · {item.created_at}</Text></View><Text className='score-badge'>{Math.round(item.accuracy)}%</Text><Icon name='arrow' size={18} /></View>)}
    {history.length < total && <Button className='text-button' disabled={loading} onClick={() => load(page + 1)}>{loading ? '正在读取' : '加载更多'}</Button>}
  </StudioShell>
}
