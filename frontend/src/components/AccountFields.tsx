import { Input, Text, View, Button } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { Credentials } from '../services/identity'

export function AccountFields({ value, onChange, nickname = false, usernameLocked = false, passwordLabel = '密码' }: {
  value: Credentials; onChange: (value: Credentials) => void; nickname?: boolean; usernameLocked?: boolean; passwordLabel?: string;
}) {
  return <View className='account-fields'>
    {nickname && <><Text className='field-label'>学园昵称</Text><Input className='studio-input' placeholder='你希望被怎样称呼' value={value.nickname} maxlength={40} onInput={e => onChange({ ...value, nickname: e.detail.value })} /></>}
    <Text className='field-label'>账号</Text><Input className='studio-input' disabled={usernameLocked} placeholder='字母、数字或 . _ -' value={value.username} maxlength={40} onInput={e => onChange({ ...value, username: e.detail.value })} />
    <Text className='field-label'>{passwordLabel}</Text><Input className='studio-input' placeholder='至少 10 个字符' password value={value.password} maxlength={128} onInput={e => onChange({ ...value, password: e.detail.value })} />
  </View>
}

export function RecoveryReceipt({ code, onContinue }: { code: string; onContinue: () => void }) {
  return <View className='recovery-receipt'>
    <Text className='section-title'>保存你的账号恢复码</Text>
    <Text className='field-hint'>仅显示这一次。忘记密码时可凭此码找回账号；不要向他人发送。</Text>
    <Text className='recovery-code' selectable>{code}</Text>
    <Button className='secondary-button' onClick={() => Taro.setClipboardData({ data: code })}>复制恢复码</Button>
    <Button className='primary-button' onClick={onContinue}>已保存，继续</Button>
  </View>
}
