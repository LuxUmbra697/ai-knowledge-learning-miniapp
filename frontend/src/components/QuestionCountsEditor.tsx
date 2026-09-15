import { View, Text, Input } from '@tarojs/components'
import { QuestionCounts, questionTypes, questionLabels, defaultCounts, countQuestions } from '../services/quizBlueprint'

export function QuestionCountsEditor({ value, onChange, disabled = false }: { value: QuestionCounts; onChange: (value: QuestionCounts) => void; disabled?: boolean }) {
  const number = (raw: string) => Math.max(0, Math.min(20, Number(raw.replace(/\D/g, '')) || 0))
  return <View className='question-counts'>
    <View className='count-total'><Text className='field-label'>题目总数</Text><Input className='studio-input count-input' type='number' aria-label='题目总数' nativeProps={process.env.TARO_ENV === 'h5' ? { 'aria-label': '题目总数' } : undefined} value={String(countQuestions(value))} disabled={disabled} maxlength={2} onInput={event => onChange(defaultCounts(Math.max(1, number(event.detail.value))))} /><Text className='muted'>上限 20</Text></View>
    <View className='count-types'>{questionTypes.map(type => <View className='count-row' key={type}><Text>{questionLabels[type]}</Text><Input className='studio-input count-input' type='number' aria-label={`${questionLabels[type]}数量`} nativeProps={process.env.TARO_ENV === 'h5' ? { 'aria-label': `${questionLabels[type]}数量` } : undefined} value={String(value[type])} maxlength={2} disabled={disabled} onInput={event => onChange({ ...value, [type]: number(event.detail.value) })} /></View>)}</View>
  </View>
}
