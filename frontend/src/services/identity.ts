import Taro from '@tarojs/taro'
import { request, LoginResponse, setToken, setCachedUser } from './api'
import { PollControl } from './polling'

export type Credentials = { username: string; password: string; nickname: string }
export type IdentityProof = { password?: string; wechat_code?: string; ticket?: string }
export type IdentityResult = LoginResponse | { status: string; ticket?: string }
export type QrPurpose = 'login' | 'recovery' | 'bind' | 'verify'
export type QrData = { ticket: string; scene: string; pair_code: string; image: string; environment: string; expires_in: number }
export type ScanData = { ticket: string; registered: boolean; purpose: QrPurpose; pair_code: string }

export function identityRequest<T>(path: string, data?: unknown, control?: PollControl) {
  return request<T>(`/user/identity/${path}`, { method: data === undefined ? 'GET' : 'POST', data, control, timeout: 30000, preserveSession: true })
}
export function saveLogin(result: LoginResponse) { setToken(result.token); setCachedUser(result.user) }
export function validateCredentials(value: Credentials) {
  if (!/^[a-zA-Z0-9_.-]{3,40}$/.test(value.username)) throw new Error('账号需为 3-40 位字母、数字或 . _ -')
  if (value.password.length < 10) throw new Error('密码至少需要 10 个字符')
  return { ...value, nickname: value.nickname.trim() || '学习者' }
}
export async function wechatProof() {
  const { code } = await Taro.login()
  if (!code) throw new Error('微信身份验证未完成，请重试')
  return { wechat_code: code }
}
