import { useEffect, useRef, useState } from 'react'
import { View, Text, Button, Image } from '@tarojs/components'
import { useDidHide } from '@tarojs/taro'
import { identityRequest, QrPurpose, QrData, IdentityProof, IdentityResult } from '../services/identity'
import { qrImage } from '../services/qrImage'
import { PollControl, pollUntil } from '../services/polling'
import { Notice } from './StudioShell'
import { Icon } from './Icon'

export function WechatQr({ purpose, proof = {}, onResult, onCancel }: {
  purpose: QrPurpose; proof?: IdentityProof; onResult: (result: IdentityResult) => void; onCancel: () => void;
}) {
  const [qr, setQr] = useState<QrData | null>(null), [source, setSource] = useState(''), [error, setError] = useState('')
  const [epoch, setEpoch] = useState(0)
  const control = useRef<PollControl>(), ticket = useRef(''), initial = useRef({ purpose, proof }), receive = useRef(onResult)
  receive.current = onResult
  const cancelRemote = () => {
    if (ticket.current) { const value = ticket.current; ticket.current = ''; void identityRequest('qr/cancel', { ticket: value }).catch(() => {}) }
  }
  useDidHide(() => { control.current?.cancel(); cancelRemote(); setError('扫码已暂停，请刷新二维码后继续') })
  useEffect(() => {
    const current = new PollControl(); control.current = current
    let release = () => {}
    setError(''); setQr(null); setSource('')
    void (async () => {
      const input = initial.current
      const path = input.purpose === 'bind' ? 'qr/bind' : input.purpose === 'verify' ? 'qr/verify' : 'qr/create'
      const data = input.purpose === 'bind' ? input.proof : input.purpose === 'verify' ? {} : { purpose: input.purpose }
      const created = await identityRequest<QrData>(path, data, current)
      ticket.current = created.ticket
      const bitmap = await qrImage(created.image); release = bitmap.release
      if (current.cancelled) { release(); cancelRemote(); return }
      setQr(created); setSource(bitmap.source)
      await pollUntil(() => identityRequest<{ status: string }>('qr/poll', { ticket: created.ticket }, current), value => value.status === 'approved', { intervalMs: 2200, maxAttempts: 135, control: current })
      const result = await identityRequest<IdentityResult>('qr/consume', { ticket: created.ticket }, current)
      ticket.current = ''; current.check(); receive.current(result)
    })().catch(reason => { if (!current.cancelled) setError(reason instanceof Error ? reason.message : '扫码未完成，请重试') })
    return () => { current.cancel(); cancelRemote(); release() }
  }, [epoch])
  return <View className='wechat-qr'>
    <Text className='section-title'>{purpose === 'bind' ? '扫描新的微信完成绑定' : purpose === 'verify' ? '验证已绑定的微信' : purpose === 'recovery' ? '微信验证找回密码' : '微信扫码登录'}</Text>
    {source && <Image className='wechat-qr-image' src={source} mode='aspectFit' />}
    {qr && <><Text className='qr-pair-code'>确认码 {qr.pair_code}</Text><Text className='field-hint'>请用微信扫码，在星知学园小程序内核对确认码。二维码 5 分钟内有效。</Text>{qr.environment !== 'release' && <Text className='field-hint'>当前为{qr.environment === 'trial' ? '体验版' : '开发版'}，仅对有权限的微信账号开放。</Text>}</>}
    {!qr && !error && <Text className='muted'>正在向微信获取二维码</Text>}
    {error && <Notice message={error} />}
    <View className='document-actions'><Button className='text-button' onClick={() => { control.current?.cancel(); cancelRemote(); onCancel() }}>取消</Button>{error && <Button className='text-button' onClick={() => setEpoch(value => value + 1)}><Icon name='refresh' size={18} />刷新二维码</Button>}</View>
  </View>
}
