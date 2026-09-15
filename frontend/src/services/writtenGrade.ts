import Taro from '@tarojs/taro'
import { request, getCachedUser, getLearningTask, getQuizDetail, getReviewResult, LearningTask, AnswerRecord, Question } from './api'
import { PollControl, pollUntil } from './polling'

export const writtenKey = (quizId: string, questionId: string) => `ai-learn:v1:written:${getCachedUser()?.id}:${quizId}:${questionId}`
export function pendingWritten(quizId: string, questionId: string): { answers: string[]; key: string; duration: number } | null {
  const saved = Taro.getStorageSync(writtenKey(quizId, questionId))
  return saved && typeof saved.key === 'string' && Array.isArray(saved.answers) && saved.answers.length === 1 && typeof saved.answers[0] === 'string' ? saved : null
}

async function wait(task: LearningTask, control: PollControl, onTask?: (task: LearningTask) => void) {
  return pollUntil(() => getLearningTask(task.task_id, control), update => {
    onTask?.(update)
    if (update.status === 'failed' || update.status === 'cancelled') throw new Error(update.error_message || '评阅未完成，原作答未被覆盖')
    return update.status === 'completed'
  }, { control, intervalMs: 1500, maxAttempts: 120 })
}

export async function submitWritten(quizId: string, questionId: string, answers: string[], duration: number, control: PollControl, onTask?: (task: LearningTask) => void) {
  const key = writtenKey(quizId, questionId)
  const pending = pendingWritten(quizId, questionId) || { answers, duration, key: `grade_${Date.now()}_${Math.random().toString(36).slice(2)}` }
  if (pending.answers[0] !== answers[0]) throw new Error('原答案的评阅尚未确认，请恢复原答案或到任务记录取消后再提交')
  Taro.setStorageSync(key, pending)
  const created = await request<LearningTask | { completed: boolean }>(`/quiz/${quizId}/answer/async`, {
    method: 'POST', idempotencyKey: pending.key, control,
    data: { question_id: questionId, selected_answers: pending.answers, duration_ms: pending.duration },
  })
  if ('task_id' in created) {
    try { await wait(created, control, onTask) }
    catch (reason) { if (!control.cancelled) Taro.removeStorageSync(key); throw reason }
  }
  const detail = await getQuizDetail(quizId)
  const record = detail.answer_records?.find(item => item.question_id === questionId)
  const question = detail.questions.find(item => item.id === questionId)
  if (!record || !question) throw new Error('评阅结果尚未保存，请刷新重试')
  Taro.removeStorageSync(key)
  return { record, question, replayed: false } as { record: AnswerRecord; question: Question; replayed: boolean }
}

export async function submitWrittenReview(cardId: string, version: number, answers: string[], control: PollControl, onTask?: (task: LearningTask) => void) {
  const key = `ai-learn:v1:written-review:${getCachedUser()?.id}:${cardId}:${version}`
  let idempotency = Taro.getStorageSync(key)
  if (!idempotency) { idempotency = `review_${Date.now()}_${Math.random().toString(36).slice(2)}`; Taro.setStorageSync(key, idempotency) }
  const created = await request<LearningTask | { completed: boolean }>(`/learning/cards/${cardId}/answer/async`, {
    method: 'POST', idempotencyKey: idempotency, control, data: { version, selected_answers: answers },
  })
  if ('task_id' in created) {
    try { await wait(created, control, onTask) }
    catch (reason) { if (!control.cancelled) Taro.removeStorageSync(key); throw reason }
  }
  const result = await getReviewResult(cardId, version, control)
  Taro.removeStorageSync(key)
  return result
}
