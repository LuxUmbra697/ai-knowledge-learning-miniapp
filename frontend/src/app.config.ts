export default defineAppConfig({
  lazyCodeLoading: 'requiredComponents',
  pages: [
    'pages/index/index',
    'pages/quiz/index',
    'pages/report/index',
    'pages/profile/index',
    'pages/knowledge/index',
    'pages/login/index',
  ],
  subPackages: [{ root: 'learning', pages: ['assistant/index', 'document/index', 'tasks/index', 'review/index', 'tutor/index', 'path/index', 'companion/index', 'security/index'] }],
  networkTimeout: {
    request: 600000,
    connectSocket: 600000,
    uploadFile: 600000,
    downloadFile: 600000,
  },
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#fff',
    navigationBarTitleText: '星知学园',
    navigationBarTextStyle: 'black',
  },
})
