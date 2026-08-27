import { useState, useCallback } from 'react'
import { View, Text, Image, Button, Input } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { getUserProfile, getQuizHistory, updateUserProfile, setCachedUser } from '../../services/api'
import type { UserProfile, QuizHistoryItem } from '../../services/api'
import './index.scss'

export default function ProfilePage() {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [historyItems, setHistoryItems] = useState<QuizHistoryItem[]>([])
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [editing, setEditing] = useState(false)

  const loadProfile = useCallback(() => {
    return getUserProfile()
      .then((data) => {
        setProfile(data)
        // 同步更新本地缓存，让首页等页面能读到最新信息
        setCachedUser({ id: data.id, nickname: data.nickname, avatar_url: data.avatar_url, total_xp: data.total_xp })
      })
      .catch(() => {})
  }, [])

  const loadHistory = useCallback((p: number, reset = false) => {
    setLoadingMore(true)
    getQuizHistory(p, 10)
      .then((data) => {
        setHistoryItems((prev) => (reset ? data.items : [...prev, ...data.items]))
        setPage(p)
        setHasMore(data.items.length >= 10 && p * 10 < data.total)
      })
      .catch(() => {})
      .finally(() => setLoadingMore(false))
  }, [])

  // 每次 tab 显示时刷新
  useDidShow(() => {
    loadProfile()
    loadHistory(1, true)
  })

  const handleLoadMore = () => {
    if (!hasMore || loadingMore) return
    loadHistory(page + 1)
  }

  const handleViewDetail = (quizId: string) => {
    Taro.navigateTo({
      url: `/pages/report/index?quizId=${quizId}`,
    })
  }

  // Bug 9: 微信头像授权
  const handleChooseAvatar = (e) => {
    const avatarUrl = e.detail.avatarUrl
    if (avatarUrl) {
      updateUserProfile({ avatar_url: avatarUrl })
        .then(() => loadProfile())
        .then(() => {})
        .catch(() => {})
    }
  }

  // Bug 9: 昵称编辑 — 微信 type='nickname' 选择后触发 onInput，自动提交
  const handleNicknameInput = (e) => {
    const name = (e?.detail?.value || '').trim()
    if (name && name !== profile?.nickname) {
      setEditing(false)
      updateUserProfile({ nickname: name })
        .then(() => loadProfile())
        .catch(() => {})
    }
  }

  return (
    <View className='profile-page'>
      <View className='profile-content'>
        <View className='avatar-section'>
          {/* Bug 8 + Bug 9: 显示真实头像，支持点击授权更换 */}
          <Button className='avatar-btn' openType='chooseAvatar' onChooseAvatar={handleChooseAvatar}>
            {profile?.avatar_url ? (
              <Image className='avatar-img' src={profile.avatar_url} mode='aspectFill' />
            ) : (
              <View className='avatar-placeholder'>
                <Text className='avatar-emoji'>{profile?.nickname?.[0] || '🎓'}</Text>
              </View>
            )}
          </Button>
          {editing ? (
            <Input
              type='nickname'
              className='nickname-input'
              onInput={(e) => handleNicknameInput(e)}
              focus
              placeholder='点击获取微信昵称'
            />
          ) : (
            <Text className='nickname' onClick={() => setEditing(true)}>
              {profile?.nickname || '学习者'}
            </Text>
          )}
          <Text className='slogan'>每天闯关一点点，进步看得见</Text>
        </View>

        <View className='stats-row'>
          <View className='stat-item'>
            <Text className='stat-num'>{profile?.quiz_count ?? 0}</Text>
            <Text className='stat-label'>闯关次数</Text>
          </View>
          <View className='stat-item'>
            <Text className='stat-num'>{profile?.correct_count ?? 0}</Text>
            <Text className='stat-label'>答对题数</Text>
          </View>
          <View className='stat-item'>
            <Text className='stat-num'>{profile?.average_accuracy ?? 0}%</Text>
            <Text className='stat-label'>平均正确率</Text>
          </View>
        </View>

        <View className='xp-row'>
          <Text className='xp-label'>经验值</Text>
          <View className='xp-value-badge'>
            <Text className='xp-value'>{profile?.total_xp ?? 0}</Text>
            <Text className='xp-star'>⭐</Text>
          </View>
        </View>

        <View
          className='knowledge-entry'
          onClick={() => Taro.navigateTo({ url: '/pages/knowledge/index' })}
        >
          <View className='knowledge-entry-left'>
            <Text className='knowledge-entry-icon'>📚</Text>
            <Text className='knowledge-entry-text'>我的知识库</Text>
          </View>
          <Text className='knowledge-entry-arrow'>›</Text>
        </View>

        {/* 闯关历史 */}
        <Text className='section-title'>闯关记录</Text>
        {historyItems.length === 0 ? (
          <View className='empty-history'>
            <Text className='empty-text'>暂无闯关记录，去首页开始学习吧</Text>
          </View>
        ) : (
          <View className='history-list'>
            {historyItems.map((item) => (
              <View
                key={item.quiz_id}
                className='history-item'
                onClick={() => handleViewDetail(item.quiz_id)}
              >
                <View className='history-left'>
                  <Text className='history-title'>{item.title}</Text>
                  <Text className='history-meta'>
                    {item.question_count} 题 · 正确率 {Math.round(item.accuracy)}%
                  </Text>
                </View>
                <Text className='history-arrow'>›</Text>
              </View>
            ))}
            {hasMore && (
              <View className='load-more' onClick={handleLoadMore}>
                <Text className='load-more-text'>{loadingMore ? '加载中...' : '加载更多'}</Text>
              </View>
            )}
          </View>
        )}
      </View>
    </View>
  )
}
