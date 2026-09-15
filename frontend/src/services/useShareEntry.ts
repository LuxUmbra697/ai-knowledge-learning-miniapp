import { useShareAppMessage } from '@tarojs/taro'
import { publicSharePayload } from './sharePayload'

export function useShareEntry() {
  useShareAppMessage(() => publicSharePayload())
}
