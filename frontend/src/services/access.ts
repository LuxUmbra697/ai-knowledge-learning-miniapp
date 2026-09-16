import Taro from '@tarojs/taro'
import { getToken } from './api'
import { isPublicPage, safeReturnPath, pageReturnPath } from './accessPolicy'

const RETURN_KEY = 'ai-learn:v1:login-return'
let pending: Promise<boolean> | null = null
function currentPath() {
  const pages = Taro.getCurrentPages(), page = pages[pages.length - 1]
  const params = Taro.getCurrentInstance().router?.params || {}
  return pageReturnPath(page?.route || 'pages/index/index', params)
}
export async function requireLogin(destination = currentPath(), returnHome = false): Promise<boolean> {
  if (getToken()) return true
  if (pending) return pending
  pending = (async () => {
    const answer = await Taro.showModal({ title: '登录后继续', content: '登录后可使用个人学习记录和学习功能。现在去登录吗？', confirmText: '去登录', cancelText: '继续浏览' })
    if (answer.confirm) {
      Taro.setStorageSync(RETURN_KEY, { path: safeReturnPath(destination), expires: Date.now() + 10 * 60 * 1000 })
      await Taro.reLaunch({ url: '/pages/login/index' })
    } else if (returnHome) await Taro.reLaunch({ url: '/pages/index/index' })
    return false
  })().finally(() => { pending = null })
  return pending
}
export function finishLogin() {
  const saved = Taro.getStorageSync(RETURN_KEY)
  Taro.removeStorageSync(RETURN_KEY)
  return Taro.reLaunch({ url: saved?.expires > Date.now() ? safeReturnPath(saved.path) : '/pages/index/index' })
}
export async function openPage(path: string) {
  if (isPublicPage(path) || await requireLogin(path)) return Taro.navigateTo({ url: path })
}
export async function navigate(path: string) {
  if (isPublicPage(path) || await requireLogin(path)) return Taro.reLaunch({ url: path })
}
