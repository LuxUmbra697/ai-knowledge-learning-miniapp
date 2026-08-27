import type { UserConfigExport } from '@tarojs/cli'

export default {
  logger: {
    quiet: false,
    stats: true,
  },
  defineConstants: {
    API_BASE_URL: '"http://localhost:8000/api/v1"',
  },
  mini: {},
  h5: {},
} satisfies UserConfigExport<'webpack5'>
