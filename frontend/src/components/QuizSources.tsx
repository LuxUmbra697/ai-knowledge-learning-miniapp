import { View, Text, Button } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { QuizSourceContext } from '../services/api'
import { Icon } from './Icon'

export function QuizSources({ source }: { source?: QuizSourceContext | null }) {
  if (!source || source.source_type === 'private_document') return null
  return <View className='quiz-evidence'>
    <Text className='muted'>{source.source_type === 'model_knowledge' ? '模型主题练习，未使用可核验的外部资料。解析可能有误，请对照教材。' : '网页仅作为出题参考，尚未完成逐题引用校验。'}</Text>
    {source.sources.map((item, index) => <View className='quiz-citation' key={index}>
      <Text className='row-title'>{item.title}</Text><Text selectable>{item.excerpt}</Text>
      <Button className='text-button' onClick={() => Taro.setClipboardData({ data: item.url }).catch(() => Taro.showToast({ title: '复制失败', icon: 'none' }))}><Icon name='arrow' size={16} />复制来源链接</Button>
    </View>)}
  </View>
}
