export default defineAppConfig({
  pages: [
    'pages/index/index',
    'pages/quiz/index',
    'pages/report/index',
    'pages/profile/index',
    'pages/knowledge/index',
  ],
  networkTimeout: {
    request: 600000,
    connectSocket: 600000,
    uploadFile: 600000,
    downloadFile: 600000,
  },
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#fff',
    navigationBarTitleText: 'LuxUmbra-AI闯关学习',
    navigationBarTextStyle: 'black',
  },
  tabBar: {
    color: '#9b7d60',
    selectedColor: '#df5f1f',
    backgroundColor: '#fffbf8',
    borderStyle: 'white',
    list: [
      {
        pagePath: 'pages/index/index',
        text: '闯关',
        iconPath: 'assets/tab-home.png',
        selectedIconPath: 'assets/tab-home-active.png',
      },
      {
        pagePath: 'pages/profile/index',
        text: '我的',
        iconPath: 'assets/tab-me.png',
        selectedIconPath: 'assets/tab-me-active.png',
      },
    ],
  },
})
