import { defineConfig, type UserConfigExport } from '@tarojs/cli'
import path from 'node:path'
import devConfig from './dev'
import prodConfig from './prod'

export default defineConfig<'webpack5'>(async (merge) => {
  const baseConfig: UserConfigExport<'webpack5'> = {
    projectName: 'frontend',
    date: '2025-04-07',
    designWidth: 375,
    deviceRatio: {
      640: 2.34 / 2,
      750: 1,
      375: 2,
      828: 1.81 / 2,
    },
    sourceRoot: 'src',
    outputRoot: `dist/${process.env.TARO_ENV || 'weapp'}`,
    plugins: ['@tarojs/plugin-framework-react'],
    defineConstants: {},
    copy: {
      patterns: [],
      options: {},
    },
    framework: 'react',
    compiler: 'webpack5',
    cache: {
      enable: false,
    },
    mini: {
      compile: { include: [path.resolve(__dirname, '../node_modules/@dagrejs')] },
      postcss: {
        pxtransform: {
          enable: true,
          config: {},
        },
        cssModules: {
          enable: false,
          config: {
            namingPattern: 'module',
            generateScopedName: '[name]__[local]___[hash:base64:5]',
          },
        },
      },
    },
    h5: {
      output: { filename: 'js/[name].[contenthash:12].js', chunkFilename: 'js/[name].[contenthash:12].js' },
      miniCssExtractPluginOption: { filename: 'css/[name].[contenthash:12].css', chunkFilename: 'css/[name].[contenthash:12].css' },
      webpackChain(chain) {
        chain.merge({ optimization: { splitChunks: { cacheGroups: {
          diagramShared: { test: /[\\/]node_modules[\\/]/, name: 'diagram-shared', chunks: 'async', minChunks: 2, priority: 30, reuseExistingChunk: true },
        } } } })
      },
      publicPath: '/ai-learn/',
      staticDirectory: 'static',
      devServer: {
        port: 10086,
        host: '127.0.0.1',
        proxy: [{ context: ['/ai-learn/api'], target: 'http://127.0.0.1:18081', pathRewrite: { '^/ai-learn/api': '/api' } }],
      },
      router: {
        mode: 'browser',
        basename: '/ai-learn',
      },
      postcss: {
        autoprefixer: {
          enable: true,
          config: {},
        },
        pxtransform: { enable: false },
        cssModules: {
          enable: false,
          config: {
            namingPattern: 'module',
            generateScopedName: '[name]__[local]___[hash:base64:5]',
          },
        },
      },
    },
  }

  if (process.env.NODE_ENV === 'development') {
    return merge({}, baseConfig, devConfig)
  }
  return merge({}, baseConfig, prodConfig)
})
