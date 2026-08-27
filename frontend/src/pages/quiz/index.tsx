import { useState, useMemo, useEffect } from 'react'
import { View, Text, Image } from '@tarojs/components'
import Taro, { useRouter } from '@tarojs/taro'
import type { Question, AnswerRecord, QuizData } from '../../services/api'
import { getCachedUser } from '../../services/api'
import './index.scss'

export default function QuizPage() {
  const router = useRouter()

  // 从路由参数解析题库数据
  const quizData: QuizData | null = useMemo(() => {
    try {
      const raw = router.params.quizData
      return raw ? JSON.parse(decodeURIComponent(raw)) : null
    } catch {
      return null
    }
  }, [router.params.quizData])

  // Bug 13: 动态设置导航栏标题
  useEffect(() => {
    if (quizData?.title) {
      Taro.setNavigationBarTitle({ title: quizData.title.slice(0, 10) })
    }
  }, [quizData?.title])

  const questions = quizData?.questions || []
  const totalQuestions = questions.length

  const [currentIndex, setCurrentIndex] = useState(0)
  const [selectedAnswers, setSelectedAnswers] = useState<string[]>([])
  const [submitted, setSubmitted] = useState(false)
  const [answerRecords, setAnswerRecords] = useState<AnswerRecord[]>([])
  const [startTime, setStartTime] = useState<number>(Date.now())
  const [correctCount, setCorrectCount] = useState(0)

  const currentQuestion: Question | undefined = questions[currentIndex]

  // 处理选项点击
  const handleOptionClick = (key: string) => {
    if (submitted) return

    if (currentQuestion?.type === 'multiple') {
      // 多选题切换选中
      setSelectedAnswers((prev) =>
        prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
      )
    } else {
      // 单选和判断题
      setSelectedAnswers([key])
    }
  }

  // 提交当前题目答案
  const handleSubmit = () => {
    if (selectedAnswers.length === 0 || !currentQuestion) return

    const isCorrect =
      currentQuestion.answer.length === selectedAnswers.length &&
      currentQuestion.answer.every((a) => selectedAnswers.includes(a))

    const duration = Date.now() - startTime

    const record: AnswerRecord = {
      question_id: currentQuestion.id,
      selected_answers: [...selectedAnswers],
      is_correct: isCorrect,
      duration_ms: duration,
    }

    setAnswerRecords((prev) => [...prev, record])
    if (isCorrect) setCorrectCount((prev) => prev + 1)
    setSubmitted(true)
  }

  // 下一题
  const handleNext = () => {
    if (currentIndex < totalQuestions - 1) {
      setCurrentIndex((prev) => prev + 1)
      setSelectedAnswers([])
      setSubmitted(false)
      setStartTime(Date.now())
    } else {
      // 所有题目完成，跳转报告页
      Taro.navigateTo({
        url: `/pages/report/index?quizData=${encodeURIComponent(JSON.stringify(quizData))}&answerRecords=${encodeURIComponent(JSON.stringify(answerRecords))}`,
      })
    }
  }

  // 上一题（仅查看，不允许修改）
  const handlePrev = () => {
    if (currentIndex > 0) {
      setCurrentIndex((prev) => prev - 1)
      // 回看上一题时以已提交状态展示
      const prevRecord = answerRecords[currentIndex - 1]
      if (prevRecord) {
        setSelectedAnswers(prevRecord.selected_answers)
        setSubmitted(true)
      }
    }
  }

  const handleClose = () => {
    Taro.navigateBack()
  }

  if (!quizData || !currentQuestion) {
    return (
      <View className='quiz-page'>
        <View className='empty-state'>
          <Text>题目加载失败</Text>
          <View className='btn-primary' style={{ marginTop: '32px', width: '300px' }} onClick={handleClose}>
            <Text>返回首页</Text>
          </View>
        </View>
      </View>
    )
  }

  const progressPercent = ((currentIndex + 1) / totalQuestions) * 100

  // 判断选项状态
  const getOptionClass = (key: string) => {
    if (!submitted) {
      return selectedAnswers.includes(key) ? 'option selected' : 'option'
    }
    const isCorrectAnswer = currentQuestion.answer.includes(key)
    const isSelected = selectedAnswers.includes(key)
    if (isCorrectAnswer) return 'option correct'
    if (isSelected && !isCorrectAnswer) return 'option wrong'
    return 'option'
  }

  const isCurrentCorrect =
    submitted &&
    currentQuestion.answer.length === selectedAnswers.length &&
    currentQuestion.answer.every((a) => selectedAnswers.includes(a))

  return (
    <View className='quiz-page'>
      {/* 顶部栏 */}
      <View className='quiz-header'>
        <Text className='question-num'>第 {currentIndex + 1} / {totalQuestions} 题</Text>
        <View className='coin-badge-small'>
          <Text className='coin-text'>{getCachedUser()?.total_xp ?? 0}</Text>
          <Text className='coin-icon'>⭐</Text>
        </View>
      </View>

      {/* 进度条 */}
      <View className='quiz-progress'>
        <View className='progress-track'>
          <View className='progress-fill' style={{ width: `${progressPercent}%` }} />
        </View>
        <View className='progress-meta'>
          <Text className='meta-text'>第 {currentIndex + 1} 题 / 共 {totalQuestions} 题</Text>
          <Text className='meta-text'>答对 {correctCount} 题</Text>
        </View>
      </View>

      {/* 题干 */}
      <Text className='quiz-title'>{currentQuestion.stem}</Text>

      {/* 题目配图（若 AI 生成了） */}
      {currentQuestion.image_url && (
        <View className='question-image-wrap'>
          <Image
            className='question-image'
            src={currentQuestion.image_url}
            mode='aspectFit'
          />
        </View>
      )}

      {/* 选项列表 */}
      <View className='options-list'>
        {currentQuestion.options.map((opt) => (
          <View
            key={opt.key}
            className={getOptionClass(opt.key)}
            onClick={() => handleOptionClick(opt.key)}
          >
            {submitted && currentQuestion.answer.includes(opt.key) && (
              <View className='check-icon'>✓</View>
            )}
            {submitted && selectedAnswers.includes(opt.key) && !currentQuestion.answer.includes(opt.key) && (
              <View className='cross-icon'>✗</View>
            )}
            <Text className='option-text'>{opt.key}. {opt.text}</Text>
          </View>
        ))}
      </View>

      {/* 未提交时显示提交按钮 */}
      {!submitted && selectedAnswers.length > 0 && (
        <View className='btn-primary submit-btn' onClick={handleSubmit}>
          <Text>确认答案</Text>
        </View>
      )}

      {/* 提交后的反馈区 */}
      {submitted && (
        <>
          {/* 结果提示 */}
          <View className={`result-tip ${isCurrentCorrect ? 'is-correct' : 'is-wrong'}`}>
            <Text className='result-label'>
              {isCurrentCorrect ? '✓ 答对啦' : '✗ 答错了'}
            </Text>
            <Text className='result-reward'>
              {isCurrentCorrect ? '+2 经验值' : '+0 经验值'}
            </Text>
          </View>

          {/* 讲解区 */}
          <View className='explain-box'>
            <Text className='explain-title'>解析：</Text>
            <Text className='explain-content'>{currentQuestion.explanation}</Text>
          </View>

          {/* 导航按钮 */}
          <View className='nav-buttons'>
            {currentIndex > 0 && (
              <View className='prev-btn' onClick={handlePrev}>
                <Text>上一题</Text>
              </View>
            )}
            <View className='next-btn' onClick={handleNext}>
              <Text>
                {currentIndex < totalQuestions - 1 ? '继续 →' : '查看报告 →'}
              </Text>
            </View>
          </View>
        </>
      )}
    </View>
  )
}
