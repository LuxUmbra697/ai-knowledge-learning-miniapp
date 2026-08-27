import { PropsWithChildren, useEffect } from 'react'
import Taro from '@tarojs/taro'
import { getToken, setToken, setCachedUser, loginByCode, resolveLogin } from './services/api'
import './app.scss'

function App({ children }: PropsWithChildren) {
  useEffect(() => {
    if (getToken()) {
      // 已有 token，直接标记就绪
      resolveLogin()
    } else {
      Taro.login({
        success: async (res) => {
          if (!res.code) { resolveLogin(); return }
          try {
            const data = await loginByCode(res.code)
            setToken(data.token)
            setCachedUser(data.user)
          } catch {
            // 登录失败不阻断核心功能
          } finally {
            resolveLogin()
          }
        },
        fail: () => resolveLogin(),
      })
    }
  }, [])

  return children
}

export default App
