import { useState, useEffect, useMemo, useRef } from 'react'
import { View, Text, Image } from '@tarojs/components'
import Taro, { useRouter } from '@tarojs/taro'
import { generateReport, getQuizDetail, getCachedUser, setCachedUser } from '../../services/api'
import type { QuizData, AnswerRecord, ReportData } from '../../services/api'
import './index.scss'

/** Bug 14: 根据正确率返回不同的评价话术 */
function getHeadingByAccuracy(acc: number): string {
  if (acc >= 100) return '🎉 满分通关，太厉害了！'
  if (acc >= 80) return '💪 表现优秀，继续保持！'
  if (acc >= 60) return '👍 你这局学得很稳'
  if (acc >= 40) return '📚 有进步空间，加油！'
  return '🌱 别灰心，下次会更好！'
}

export default function ReportPage() {
  const router = useRouter()

  // 路径 A：从闯关页传入完整数据
  const fromQuiz = useMemo(() => {
    try {
      const qd = router.params.quizData
        ? JSON.parse(decodeURIComponent(router.params.quizData))
        : null
      const ar = router.params.answerRecords
        ? JSON.parse(decodeURIComponent(router.params.answerRecords))
        : []
      return { quizData: qd as QuizData | null, answerRecords: ar as AnswerRecord[] }
    } catch {
      return { quizData: null, answerRecords: [] }
    }
  }, [router.params])

  // 路径 B：从历史记录进入（只有 quizId）
  const quizIdFromHistory = router.params.quizId || ''

  const [quizData, setQuizData] = useState<QuizData | null>(fromQuiz.quizData)
  const [answerRecords, setAnswerRecords] = useState<AnswerRecord[]>(fromQuiz.answerRecords)
  const [report, setReport] = useState<ReportData | null>(null)
  const [loading, setLoading] = useState(true)
  const [xpGain, setXpGain] = useState<number | null>(null)
  const loadedRef = useRef(false)

  // 本地计算基础统计
  const localAccuracy = useMemo(() => {
    if (answerRecords.length === 0) return 0
    const correct = answerRecords.filter((r) => r.is_correct).length
    return Math.round((correct / answerRecords.length) * 100)
  }, [answerRecords])

  useEffect(() => {
    // 防止重复加载（Bug 17 修复）
    if (loadedRef.current) return
    loadedRef.current = true

    // 路径 B：从历史进入，通过 API 获取所有数据
    if (quizIdFromHistory && !fromQuiz.quizData) {
      getQuizDetail(quizIdFromHistory)
        .then((detail) => {
          setQuizData({
            quiz_id: detail.quiz_id,
            title: detail.title,
            summary: detail.summary,
            questions: detail.questions as any,
          })
          if (detail.answer_records) setAnswerRecords(detail.answer_records)
          if (detail.report) setReport(detail.report as any)
        })
        .catch(() => {})
        .finally(() => setLoading(false))
      return
    }

    // 路径 A：从闯关页进入，调用 AI 生成报告
    if (!fromQuiz.quizData) {
      setLoading(false)
      return
    }

    const fetchReport = async () => {
      try {
        const data = await generateReport({
          quiz_id: fromQuiz.quizData!.quiz_id,
          topic: fromQuiz.quizData!.title,
          questions: fromQuiz.quizData!.questions,
          answer_records: fromQuiz.answerRecords,
        })
        setReport(data)

        // 计算 XP 增量并刷新缓存
        const correctCount = fromQuiz.answerRecords.filter((r) => r.is_correct).length
        const gained = 10 + correctCount * 2
        setXpGain(gained)
        const cached = getCachedUser()
        if (cached) {
          cached.total_xp += gained
          setCachedUser(cached)
        }
      } catch {
        setReport(null)
      } finally {
        setLoading(false)
      }
    }

    fetchReport()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const accuracy = report?.accuracy ?? localAccuracy

  const handleGoHome = () => {
    Taro.switchTab({ url: '/pages/index/index' })
  }

  const handleGeneratePoster = () => {
    Taro.showToast({ title: '海报功能开发中', icon: 'none' })
  }

  return (
    <View className='report-page'>
      {/* 顶部栏 */}
      <View className='report-toolbar'>
        <Text className='toolbar-title'>{quizData?.title || '闯关报告'}</Text>
        {xpGain !== null && (
          <View className='xp-badge'>
            <Text className='xp-text'>+{xpGain} XP</Text>
          </View>
        )}
      </View>

      {/* 主标题 — Bug 14: 根据正确率动态评价 */}
      <Text className='report-heading'>{getHeadingByAccuracy(accuracy)}</Text>
      <Text className='report-subtitle'>先看结果，再看错因，最后给你下一步建议。</Text>

      {/* 标签 — Bug 16: 绿色表示掌握度，红色表示错题 */}
      <View className='tag-row'>
        <View className='tag tag-green'>
          <Text>✅ 答对 {answerRecords.filter((r) => r.is_correct).length} 题</Text>
        </View>
        <View className='tag tag-red'>
          <Text>❌ 答错 {answerRecords.filter((r) => !r.is_correct).length} 题</Text>
        </View>
      </View>

      {loading ? (
        <View className='loading-state'>
          <Text>AI 正在生成报告...</Text>
        </View>
      ) : (
        <>
          {/* 掌握度卡片 */}
          <View className='note-card'>
            <Text className='card-title'>🕐 掌握度</Text>
            <View className='mastery-row'>
              <View className='mastery-ring'>
                <View
                  className='ring-outer-large'
                  style={{
                    background: `conic-gradient(#ff7a2f 0 ${accuracy}%, #ece7de ${accuracy}% 100%)`,
                  }}
                >
                  <View className='ring-inner-large'>
                    <Text className='ring-value'>{accuracy}%</Text>
                  </View>
                </View>
              </View>
              <View className='mastery-detail'>
                <Text className='mastery-desc'>
                  {report?.three_line_summary?.[0] ||
                    `本次答对 ${answerRecords.filter((r) => r.is_correct).length} 题，正确率 ${accuracy}%`}
                </Text>
                <View className='mastery-bar'>
                  <View className='mastery-fill' style={{ width: `${accuracy}%` }} />
                </View>
              </View>
            </View>
          </View>

          {/* 薄弱知识点 */}
          {report?.weak_points && report.weak_points.length > 0 && (
            <View className='note-card'>
              <Text className='card-title'>⚠ 最该补的 {report.weak_points.length} 点</Text>
              <View className='weak-list'>
                {report.weak_points.map((point, i) => (
                  <Text key={i} className='weak-item'>
                    {i + 1}. {point}
                  </Text>
                ))}
              </View>
            </View>
          )}

          {/* 知识总结 */}
          {report?.three_line_summary && (
            <View className='note-card'>
              <Text className='card-title'>📝 知识总结</Text>
              <View className='summary-list'>
                {report.three_line_summary.map((line, i) => (
                  <Text key={i} className='summary-item'>
                    {line}
                  </Text>
                ))}
              </View>
            </View>
          )}

          {/* 建议 */}
          {report?.advice && report.advice.length > 0 && (
            <View className='note-card'>
              <Text className='card-title'>💡 建议</Text>
              <View className='advice-list'>
                {report.advice.map((item, i) => (
                  <Text key={i} className='advice-item'>
                    • {item}
                  </Text>
                ))}
              </View>
            </View>
          )}

          {/* 分享海报 */}
          <View className='sticker-card'>
            <Text className='card-title'>🔗 分享海报</Text>
            <View className='poster-preview'>
              <Text className='poster-quote'>
                {report?.share_quote || '今天我又闯过一个知识关卡！'}
              </Text>
              <View className='poster-qr' />
            </View>
          </View>

          {/* 题目回顾（含 AI 配图，历史回看时也可查看） */}
          {quizData?.questions && quizData.questions.length > 0 && (
            <View className='note-card'>
              <Text className='card-title'>📖 题目回顾</Text>
              <View className='review-list'>
                {quizData.questions.map((q, i) => {
                  const record = answerRecords.find((r) => r.question_id === q.id)
                  return (
                    <View key={q.id} className='review-item'>
                      <Text className='review-stem'>
                        {i + 1}. {q.stem}
                      </Text>
                      {q.image_url && (
                        <Image className='review-image' src={q.image_url} mode='aspectFit' />
                      )}
                      {record && (
                        <Text className={`review-result ${record.is_correct ? 'is-correct' : 'is-wrong'}`}>
                          {record.is_correct ? '✓ 答对了' : '✗ 答错了'}
                        </Text>
                      )}
                      <Text className='review-explanation'>{q.explanation}</Text>
                    </View>
                  )
                })}
              </View>
            </View>
          )}
        </>
      )}

      {/* 底部按钮 */}
      <View className='bottom-actions'>
        <View className='btn-primary action-btn' onClick={handleGoHome}>
          <Text>再来一组</Text>
        </View>
        <View className='btn-secondary action-btn' onClick={handleGeneratePoster}>
          <Text>生成海报</Text>
        </View>
      </View>
    </View>
  )
}
