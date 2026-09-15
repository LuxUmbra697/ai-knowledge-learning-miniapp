import { View, Text, Input, Textarea } from '@tarojs/components'
import { AnswerRecord, Question } from '../services/api'

export const answerComplete = (question: Question, values: string[]) => {
  const count = question.type === 'fill' ? question.blank_count || question.answer?.length || 1 : 1
  return question.type === 'fill' || question.type === 'written' ? values.length === count && values.every(value => !!value.trim()) : values.length > 0
}
export function TextAnswer({ question, values, disabled, onChange }: { question: Question; values: string[]; disabled: boolean; onChange: (value: string[]) => void }) {
  if (question.type === 'written') return <View className='text-answer'><Text className='muted'>问答评阅 · 按评分要点逐项核对，模型判断可能有误</Text><Textarea className='studio-textarea written-answer' placeholder='写下你的理解' aria-label='问答题答案' nativeProps={process.env.TARO_ENV === 'h5' ? { 'aria-label': '问答题答案' } : undefined} value={values[0] || ''} maxlength={4000} disabled={disabled} onInput={event => onChange([event.detail.value])} /><Text className='field-hint'>{(values[0] || '').length}/4000</Text></View>
  if (question.type !== 'fill') return null
  return <View className='text-answer'>{Array.from({ length: question.blank_count || question.answer?.length || 1 }, (_, index) => <View key={index}><Text className='field-label'>第 {index + 1} 空</Text><Input className='studio-input' aria-label={`第 ${index + 1} 空答案`} nativeProps={process.env.TARO_ENV === 'h5' ? { 'aria-label': `第 ${index + 1} 空答案` } : undefined} placeholder={`填写第 ${index + 1} 空`} value={values[index] || ''} maxlength={200} disabled={disabled} onInput={event => { const next = Array.from({ length: question.blank_count || question.answer?.length || 1 }, (_, i) => values[i] || ''); next[index] = event.detail.value; onChange(next) }} /></View>)}</View>
}
export function GradingFeedback({ record }: { record: AnswerRecord }) {
  const feedback = record.grading
  if (!feedback) return null
  return <View className='grading-feedback'><Text className='muted'>{feedback.method === 'model-rubric-v1' ? '模型按要点评阅 · 全部要点满足且无矛盾才计为答对' : '填空判分 · 忽略大小写、全半角和空白差异，按空的顺序匹配'}</Text>{feedback.feedback && <Text>{feedback.feedback}</Text>}{feedback.criteria?.map(item => <View key={item.index}><Text className='field-label'>要点 {item.index + 1} · {item.met ? '已覆盖' : '待补充'}</Text>{item.quote && <Text className='citation-quote'>{item.quote}</Text>}<Text>{item.feedback}</Text></View>)}</View>
}
