import type { UserConfigExport } from '@tarojs/cli'

export default {
  logger: {
    quiet: false,
    stats: true,
  },
  defineConstants: {
    API_BASE_URL: JSON.stringify(process.env.TARO_ENV === 'h5' ? '/ai-learn/api/v1' : 'http://127.0.0.1:18081/api/v1'),
  },
  mini: {},
  h5: {},
} satisfies UserConfigExport<'webpack5'>
