import { useState, useRef } from 'react'
import { View, Text, Input, Button } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { StudioShell, Notice, navigate } from '../../components/StudioShell'
import { request, setToken, setCachedUser, LoginResponse, loginByCode } from '../../services/api'

export default function LoginPage() {
  const [register, setRegister] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [nickname, setNickname] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const lock = useRef(false)
  const submit = async () => {
    if (lock.current) return
    lock.current = true; setBusy(true); setError('')
    try {
      let result: LoginResponse
      if (process.env.TARO_ENV === 'weapp') {
        const { code } = await Taro.login()
        result = await loginByCode(code)
      } else {
        if (!/^[a-zA-Z0-9_.-]{3,40}$/.test(username)) throw new Error('账号需为 3-40 位字母、数字或 . _ -')
        if (password.length < 10) throw new Error('密码至少需要 10 个字符')
        result = await request<LoginResponse>(`/user/account/${register ? 'register' : 'login'}`, {
          method: 'POST', data: { username, password, nickname: nickname.trim() || '学习者' },
        })
      }
      setToken(result.token); setCachedUser(result.user)
      navigate('/pages/index/index')
    } catch (reason) { setError(reason instanceof Error ? reason.message : '登录失败，请重试') }
    finally { lock.current = false; setBusy(false) }
  }
  return <StudioShell title='欢迎来到星知学园' subtitle='把好奇变成理解，把练习变成成长。' guest>
    <View className='login-form'>
      {process.env.TARO_ENV === 'h5' && <>
        <View className='login-switch'><Button className={!register ? 'active' : ''} onClick={() => { setRegister(false); setError('') }}>登录学园</Button><Button className={register ? 'active' : ''} onClick={() => { setRegister(true); setError('') }}>创建账号</Button></View>
        {register && <><Text className='field-label'>学园昵称</Text><Input className='studio-input' placeholder='你希望被怎样称呼' value={nickname} maxlength={40} onInput={e => setNickname(e.detail.value)} /></>}
        <Text className='field-label'>账号</Text><Input className='studio-input' placeholder='字母、数字或 . _ -' value={username} maxlength={40} onInput={e => setUsername(e.detail.value)} />
        <Text className='field-label'>密码</Text><Input className='studio-input' placeholder='至少 10 个字符' password value={password} maxlength={128} onInput={e => setPassword(e.detail.value)} onConfirm={submit} />
      </>}
      {error && <Notice message={error} />}
      <Button className='primary-button login-submit' disabled={busy} onClick={submit}>{busy ? '正在登录…' : process.env.TARO_ENV === 'weapp' ? '微信登录' : register ? '开启我的学习旅程' : '进入学园'}</Button>
      <Text className='field-hint' style={{ marginTop: '16px' }}>学习材料和答题记录仅对当前账号可见。</Text>
    </View>
  </StudioShell>
}
