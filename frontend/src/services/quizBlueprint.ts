export const questionTypes = ['single', 'multiple', 'judge', 'fill', 'written'] as const
export type QuestionType = typeof questionTypes[number]
export type QuestionCounts = Record<QuestionType, number>
export const questionLabels: Record<QuestionType, string> = { single: '单选题', multiple: '多选题', judge: '判断题', fill: '填空题', written: '问答题' }
export const defaultCounts = (total = 5): QuestionCounts => {
  const minority = total < 3 ? 0 : Math.max(1, Math.floor(total / 5))
  return { single: total - minority * 2, multiple: minority, judge: minority, fill: 0, written: 0 }
}
export const countQuestions = (value: QuestionCounts) => questionTypes.reduce((sum, type) => sum + value[type], 0)
export const validCounts = (value: QuestionCounts) => questionTypes.every(type => Number.isInteger(value[type]) && value[type] >= 0 && value[type] <= 20) && countQuestions(value) >= 1 && countQuestions(value) <= 20
