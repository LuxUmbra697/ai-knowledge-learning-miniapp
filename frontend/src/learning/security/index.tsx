import { requireLogin } from '../../services/access'
import { useRef, useState } from 'react'
import Taro, { useDidShow, useDidHide } from '@tarojs/taro'
import { View, Text, Button, Input } from '@tarojs/components'
import { StudioShell, Notice, navigate } from '../../components/StudioShell'
import { AccountFields, RecoveryReceipt } from '../../components/AccountFields'
import { Icon } from '../../components/Icon'
import { getToken, LoginResponse } from '../../services/api'
import { Credentials, IdentityProof, identityRequest, saveLogin, validateCredentials, wechatProof } from '../../services/identity'

export default function SecurityPage() {
  const [profile, setProfile] = useState<{ username: string | null; wechat_bound: boolean; recovery_ready: boolean } | null>(null)
  const [value, setValue] = useState<Credentials>({ username: '', password: '', nickname: '学习者' })
  const [currentPassword, setCurrentPassword] = useState(''), [confirm, setConfirm] = useState('')
  const [method, setMethod] = useState<'password' | 'wechat'>('password'), [proof, setProof] = useState<IdentityProof>({})
  const [receipt, setReceipt] = useState('')
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), lock = useRef(false), live = useRef(true)
  const load = async () => {
    if (!getToken()) { await requireLogin(undefined, true); return }
    try {
      const result = await identityRequest<NonNullable<typeof profile>>('security')
      if (!live.current) return
      setProfile(result); setValue(previous => ({ ...previous, username: result.username || '' }))
      if (!result.username && process.env.TARO_ENV === 'weapp') setMethod('wechat')
    } catch (reason) { if (live.current) setError(reason instanceof Error ? reason.message : '读取账号失败') }
  }
  useDidShow(() => { live.current = true; void load() })
  useDidHide(() => { live.current = false; setProof({}); setCurrentPassword('') })
  const run = async (action: () => Promise<void>) => {
    if (lock.current) return
    lock.current = true; setBusy(true); setError('')
    try { await action() } catch (reason) { if (live.current) setError(reason instanceof Error ? reason.message : '操作未完成') }
    finally { lock.current = false; if (live.current) setBusy(false) }
  }
  const getProof = async (): Promise<IdentityProof> => {
    if (method === 'password') {
      if (!currentPassword) throw new Error('请先输入当前密码')
      return { password: currentPassword }
    }
    if (process.env.TARO_ENV === 'weapp') return wechatProof()
    if (!proof.ticket) throw new Error('请使用账号密码验证身份')
    return proof
  }
  const changed = (result: LoginResponse) => {
    saveLogin(result); setProof({}); setCurrentPassword(''); setValue(previous => ({ ...previous, password: '' })); setConfirm('')
    if (result.recovery_code) setReceipt(result.recovery_code)
    void load()
  }
  const save = () => run(async () => {
    const credentials = validateCredentials(value)
    if (credentials.password !== confirm) throw new Error('两次输入的密码不一致')
    changed(await identityRequest<LoginResponse>('credentials', { credentials, ...await getProof() }))
    await Taro.showToast({ title: '账号密码已更新', icon: 'success' })
  })
  const bind = () => run(async () => {
    if (process.env.TARO_ENV !== 'weapp') return
    if (!currentPassword) { setMethod('password'); throw new Error('绑定或换绑前，请先填写当前账号密码') }
    const answer = await Taro.showModal({ title: profile?.wechat_bound ? '换绑当前微信' : '绑定当前微信', content: '将当前微信绑定到这个学园账号。若更换了微信，原微信将不能继续登录；学习记录不变。' })
    if (!answer.confirm) return
    const code = await wechatProof()
    changed(await identityRequest<LoginResponse>('wechat/bind-current', { ...code, password: currentPassword }))
    await Taro.showToast({ title: '微信绑定已更新', icon: 'success' })
  })
  return <StudioShell title='账号安全' subtitle='同一个学园账号，同一份学习记录。' active='profile'>
    {receipt ? <RecoveryReceipt code={receipt} onContinue={() => setReceipt('')} /> : <>
      <View className='security-summary'><Text>微信：{profile?.wechat_bound ? '已绑定' : '未绑定'}</Text><Text>恢复码：{profile?.recovery_ready ? '已设置' : '未设置'}</Text></View>
      <View className='security-section'><Text className='section-title'>验证当前身份</Text>
        <View className='login-switch'>{profile?.username && <Button className={method === 'password' ? 'active' : ''} onClick={() => { setMethod('password'); setProof({}) }}>当前密码</Button>}{process.env.TARO_ENV === 'weapp' && profile?.wechat_bound && <Button className={method === 'wechat' ? 'active' : ''} onClick={() => setMethod('wechat')}>已绑定微信</Button>}</View>
        {method === 'password' ? <Input className='studio-input' password placeholder='输入当前密码' value={currentPassword} maxlength={128} onInput={e => setCurrentPassword(e.detail.value)} /> : <Text className='field-hint'>提交时会通过当前微信验证身份。</Text>}
      </View>
      <View className='security-section'><Text className='section-title'>{profile?.username ? '修改密码' : '设置账号和密码'}</Text><AccountFields value={value} onChange={setValue} usernameLocked={!!profile?.username} passwordLabel='新密码' /><Text className='field-label'>确认新密码</Text><Input className='studio-input' password placeholder='再次输入新密码' value={confirm} maxlength={128} onInput={e => setConfirm(e.detail.value)} /><Button className='primary-button' disabled={busy || !profile} onClick={save}>保存账号密码</Button></View>
      <View className='security-section'><Text className='section-title'>账号恢复方式</Text><View className='document-actions'>{process.env.TARO_ENV === 'weapp' && <Button className='secondary-button' disabled={busy || !profile?.username} onClick={bind}><Icon name='refresh' size={18} />{profile?.wechat_bound ? '换绑当前微信' : '绑定当前微信'}</Button>}<Button className='text-button' disabled={busy || !profile?.username} onClick={() => run(async () => { const result = await identityRequest<{ recovery_code: string }>('recovery-code', await getProof()); setProof({}); setReceipt(result.recovery_code); await load() })}>生成新恢复码</Button></View><Text className='field-hint'>新恢复码会替代旧码。改密码后，其他设备需要重新登录。微信绑定在小程序内验证账号密码后操作。</Text></View>
    </>}
    {error && <Notice message={error} />}
    <Button className='text-button' onClick={() => navigate('/pages/profile/index')}>返回学习档案</Button>
  </StudioShell>
}
