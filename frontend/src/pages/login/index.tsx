import { useState, useRef } from 'react'
import { View, Text, Input, Button, Switch } from '@tarojs/components'
import { useRouter, useDidHide, useDidShow } from '@tarojs/taro'
import { StudioShell, Notice, navigate } from '../../components/StudioShell'
import { request, LoginResponse, loginByCode, clearToken } from '../../services/api'
import { AccountFields, RecoveryReceipt } from '../../components/AccountFields'
import { WechatQr } from '../../components/WechatQr'
import { Credentials, IdentityResult, ScanData, identityRequest, saveLogin, validateCredentials, wechatProof } from '../../services/identity'

export default function LoginPage() {
  const scene = useRouter().params.scene
  const [mode, setMode] = useState<'login' | 'register' | 'wechat' | 'recover'>(process.env.TARO_ENV === 'weapp' ? 'wechat' : 'login')
  const [value, setValue] = useState<Credentials>({ username: '', password: '', nickname: '' })
  const [confirm, setConfirm] = useState(''), [recovery, setRecovery] = useState(''), [recoveryTicket, setRecoveryTicket] = useState('')
  const [receipt, setReceipt] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const [resetDone, setResetDone] = useState(false)
  const [choice, setChoice] = useState(''), [decision, setDecision] = useState<'register' | 'link'>('register')
  const [withAccount, setWithAccount] = useState(false), [qr, setQr] = useState(false), [qrRecover, setQrRecover] = useState(false)
  const [scan, setScan] = useState<ScanData | null>(null), [approved, setApproved] = useState('')
  const lock = useRef(false), active = useRef(true)
  useDidShow(() => { active.current = true })
  useDidHide(() => { active.current = false; setQr(false); setQrRecover(false) })
  const finish = (result: IdentityResult) => {
    if (!active.current) return
    if ('token' in result) {
      saveLogin(result)
      if (result.recovery_code) setReceipt(result.recovery_code)
      else navigate('/pages/index/index')
    } else if (result.status === 'choice' && result.ticket) setChoice(result.ticket)
    else if (result.status === 'verified' && result.ticket) { setRecoveryTicket(result.ticket); setQrRecover(false) }
  }
  const run = async (action: () => Promise<void>) => {
    if (lock.current) return
    lock.current = true; setBusy(true); setError('')
    try { await action() } catch (reason) { if (active.current) setError(reason instanceof Error ? reason.message : '操作失败，请重试') }
    finally { lock.current = false; if (active.current) setBusy(false) }
  }
  const credentials = () => validateCredentials(value)
  const submit = () => run(async () => {
    if (mode === 'recover') {
      const input = credentials()
      if (input.password !== confirm) throw new Error('两次输入的密码不一致')
      await identityRequest('password/reset', { username: input.username, password: input.password, recovery_code: recovery, ticket: recoveryTicket })
      clearToken(); setRecovery(''); setRecoveryTicket(''); setValue({ ...value, password: '' }); setConfirm(''); setMode('login')
      setResetDone(true)
    } else {
      finish(await request<LoginResponse>('/user/account/' + (mode === 'register' ? 'register' : 'login'), { method: 'POST', data: credentials(), preserveSession: true }))
    }
  })
  const wxLogin = () => run(async () => {
    const { wechat_code } = await wechatProof()
    finish(await loginByCode(wechat_code))
  })
  const decide = (action: 'register' | 'link' | 'cancel') => run(async () => {
    const input = action !== 'cancel' && (action === 'link' || withAccount) ? credentials() : undefined
    const result = await identityRequest<IdentityResult>('wechat/finish', { ticket: choice, action, credentials: input })
    setChoice(''); if (action !== 'cancel') finish(result)
  })
  const scanCode = () => run(async () => {
    if (!scene || !/^[a-f0-9]{32}$/.test(scene)) throw new Error('二维码参数无效，请重新扫码')
    const { wechat_code } = await wechatProof()
    setScan(await identityRequest<ScanData>('qr/scan', { scene, code: wechat_code }))
  })
  const approve = (action: string) => run(async () => {
    if (!scan) return
    const input = action !== 'cancel' && (action === 'link' || (action === 'register' && withAccount)) ? credentials() : undefined
    await identityRequest('qr/approve', { ticket: scan.ticket, action, credentials: input })
    setScan(null); setApproved(action === 'cancel' ? '已取消，网页不会登录或绑定' : '已确认，请返回刚才的网页查看结果')
  })
  const choices = <>
    <View className='login-switch'><Button className={decision === 'register' ? 'active' : ''} disabled={busy} onClick={() => setDecision('register')}>注册新账号</Button><Button className={decision === 'link' ? 'active' : ''} disabled={busy} onClick={() => setDecision('link')}>绑定已有账号</Button></View>
    {decision === 'register' && <View className='setting-row'><Text>同时设置账号密码</Text><Switch checked={withAccount} onChange={e => setWithAccount(e.detail.value)} /></View>}
    {(decision === 'link' || withAccount) && <AccountFields value={value} onChange={setValue} nickname={decision === 'register'} />}
  </>
  const switchMode = (next: typeof mode) => { setMode(next); setQr(false); setQrRecover(false); setError('') }
  return <StudioShell title={scene && process.env.TARO_ENV === 'weapp' ? '微信身份确认' : '欢迎来到星知学园'} subtitle='把好奇变成理解，把练习变成成长。' guest>
    <View className='login-form'>
      {resetDone && <View className='account-success'><Text className='section-title'>密码已重置</Text><Text>原有设备的登录已失效，请使用新密码登录。</Text></View>}
      {receipt ? <RecoveryReceipt code={receipt} onContinue={() => { setReceipt(''); navigate('/pages/index/index') }} /> : scene && process.env.TARO_ENV === 'weapp' ? <>
        {approved ? <><Text>{approved}</Text><Button className='text-button' onClick={() => navigate('/pages/index/index')}>返回学园</Button></> : scan ? <>
          <Text className='qr-pair-code'>确认码 {scan.pair_code}</Text>
          <Text className='field-hint'>仅确认你本人打开的星知学园网页，请核对网页上的确认码。</Text>
          {scan.purpose === 'login' && !scan.registered ? <><Text>这个微信尚未登记，请选择</Text>{choices}<Button className='primary-button' disabled={busy} onClick={() => approve(decision)}>{decision === 'link' ? '验证并绑定已有账号' : '确认注册并登录网页'}</Button></> : <Button className='primary-button' disabled={busy} onClick={() => approve(scan.purpose === 'login' ? 'login' : scan.purpose === 'bind' ? 'bind' : 'confirm')}>{scan.purpose === 'bind' ? '确认将此微信绑定到网页账号' : scan.purpose === 'login' ? '确认登录网页' : '确认身份验证'}</Button>}
          {scan.purpose === 'bind' && <Text className='field-hint'>绑定成功后原微信将不能登录该账号，学习记录仍归原账号所有。</Text>}
          <Button className='text-button' disabled={busy} onClick={() => approve('cancel')}>取消</Button>
        </> : <><Text className='field-hint'>继续后核对网页确认码，再选择是否允许本次操作。</Text><Button className='primary-button' disabled={busy} onClick={scanCode}>验证微信身份</Button><Button className='text-button' onClick={() => navigate('/pages/index/index')}>取消</Button></>}
      </> : choice ? <><Text className='section-title'>这个微信还没有学园账号</Text>{choices}<Button className='primary-button' disabled={busy} onClick={() => decide(decision)}>{decision === 'link' ? '验证并绑定' : '确认注册'}</Button><Button className='text-button' disabled={busy} onClick={() => decide('cancel')}>取消</Button></> : <>
        <View className='login-switch'><Button disabled={busy} className={mode === 'login' ? 'active' : ''} onClick={() => switchMode('login')}>账号登录</Button><Button disabled={busy} className={mode === 'wechat' ? 'active' : ''} onClick={() => switchMode('wechat')}>微信登录</Button><Button disabled={busy} className={mode === 'register' ? 'active' : ''} onClick={() => switchMode('register')}>注册账号</Button></View>
        {mode === 'wechat' ? process.env.TARO_ENV === 'weapp' ? <Button className='primary-button login-submit' disabled={busy} onClick={wxLogin}>{busy ? '正在验证' : '微信登录'}</Button> : qr ? <WechatQr purpose='login' onResult={finish} onCancel={() => setQr(false)} /> : <Button className='primary-button login-submit' onClick={() => setQr(true)}>微信扫码登录</Button> : <>
          {mode === 'recover' && <Text className='section-title'>找回密码</Text>}
          <AccountFields value={value} onChange={setValue} nickname={mode === 'register'} passwordLabel={mode === 'recover' ? '新密码' : '密码'} />
          {mode === 'recover' && <>
            <Text className='field-label'>确认新密码</Text><Input className='studio-input' password placeholder='再次输入新密码' value={confirm} maxlength={128} onInput={e => setConfirm(e.detail.value)} />
            {!recoveryTicket ? <><Text className='field-label'>账号恢复码</Text><Input className='studio-input' password placeholder='注册或账号安全中保存的恢复码' value={recovery} maxlength={100} onInput={e => setRecovery(e.detail.value)} /><Button className='text-button' disabled={busy} onClick={() => process.env.TARO_ENV === 'weapp' ? run(async () => { const { wechat_code } = await wechatProof(); finish(await identityRequest('wechat/recover', { code: wechat_code })) }) : setQrRecover(true)}>改用已绑定微信验证</Button></> : <Text className='field-hint'>微信身份已验证，请在 5 分钟内设置新密码。</Text>}
            {qrRecover && <WechatQr purpose='recovery' onResult={finish} onCancel={() => setQrRecover(false)} />}
          </>}
          <Button className='primary-button login-submit' disabled={busy} onClick={submit}>{busy ? '正在提交' : mode === 'register' ? '开启我的学习旅程' : mode === 'recover' ? '重置密码' : '进入学园'}</Button>
        </>}
        {mode !== 'recover' && <Button className='text-button' disabled={busy} onClick={() => switchMode('recover')}>忘记密码</Button>}
      </>}
      {error && <Notice message={error} />}
      <Text className='field-hint' style={{ marginTop: '16px' }}>学习材料和答题记录仅对当前账号可见。</Text>
    </View>
  </StudioShell>
}
