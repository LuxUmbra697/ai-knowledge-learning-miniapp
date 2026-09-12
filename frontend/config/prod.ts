import type { UserConfigExport } from '@tarojs/cli'

export default {
  defineConstants: {
    API_BASE_URL: JSON.stringify(process.env.TARO_ENV === 'h5' ? '/ai-learn/api/v1' : 'https://lux-umbra.xyz/ai-learn/api/v1'),
  },
  mini: {},
  h5: {},
} satisfies UserConfigExport<'webpack5'>
