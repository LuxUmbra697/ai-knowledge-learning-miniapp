import { PropsWithChildren, useState } from 'react'
import { View, Text, Button, Switch, Image } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { themes, useStudio } from './StudioProvider'
import { Icon } from './Icon'
import Companion from './companion/Companion'
import { useCompanion } from './companion/useCompanion'

export const navigation = [
  { key: 'home', label: '学习首页', icon: 'home', path: '/pages/index/index' },
  { key: 'knowledge', label: '知识书架', icon: 'library', path: '/pages/knowledge/index' },
  { key: 'assistant', label: '学习助手', icon: 'chat', path: '/learning/assistant/index' },
  { key: 'profile', label: '学习档案', icon: 'user', path: '/pages/profile/index' },
]
export function navigate(path: string) { Taro.reLaunch({ url: path }) }

export function StudioShell({ children, active, title, subtitle, guest = false, focus = false, compact = false }: PropsWithChildren<{
  active?: string; title: string; subtitle?: string; guest?: boolean; focus?: boolean; compact?: boolean
}>) {
  const settings = useStudio()
  const [appearance, setAppearance] = useState(false)
  const [floatingSafe, setFloatingSafe] = useState(true)
  const [expanded, setExpanded] = useState(false)
  const [detached, setDetached] = useState(false)
  const portrait = useCompanion(!guest && !appearance && settings.companion)
  const reserved = (focus && !detached) || !floatingSafe
  const floating = settings.companion && (!focus || detached) && !settings.companionFolded
  const shown = settings.companion && (reserved ? expanded : !settings.companionFolded)
  const partnerLabel = !settings.companion ? '显示学习伙伴' : shown ? '收起学习伙伴' : '展开学习伙伴'
  const togglePartner = () => {
    if (!settings.companion) { settings.update({ companion: true, companionFolded: false }); return }
    if (reserved) { settings.update({ companionFolded: expanded }); setExpanded(value => !value) }
    else settings.update({ companionFolded: !settings.companionFolded })
  }
  return <View className={`studio theme-${settings.theme} ${guest ? 'studio-guest' : ''} ${compact ? 'studio-compact' : ''} ${settings.reducedMotion ? 'reduced-motion' : ''} ${floating && !guest ? 'has-companion' : ''}`}>
    {guest && <Image className='academy-background' src={require('../assets/academy-gate.jpg')} mode='aspectFill' aria-hidden />}
    <View className='studio-topbar'>
      <View className='studio-brand' onClick={() => navigate('/pages/index/index')}>
        <View className='brand-mark'><Icon name='book' size={22} /></View>
        <View><Text className='brand-name'>星知学园</Text><Text className='brand-english'>LEARNING NOTEBOOK</Text></View>
      </View>
      <View className='topbar-end'>
        <Text className='theme-caption'>{themes.find(t => t.id === settings.theme)?.name}</Text>
        {!guest && <Button className='icon-button companion-dock' aria-label={partnerLabel} data-state={!settings.companion ? 'hidden' : shown ? 'expanded' : 'folded'} onClick={togglePartner}>
          {settings.companion ? <Image src={portrait.source} mode='aspectFit' /> : <Icon name='user' />}
          <Text className='tooltip'>{partnerLabel}</Text>
        </Button>}
        <Button className='icon-button' aria-label='外观设置' onClick={() => setAppearance(true)}><Icon name='settings' /><Text className='tooltip'>外观设置</Text></Button>
      </View>
    </View>
    <View className={`studio-layout ${guest ? 'guest-layout' : ''}`}>
      {!guest && <View className='studio-sidebar'>
        <Text className='sidebar-label'>我的学习空间</Text>
        {navigation.map(item => <Button key={item.key} className={`nav-link ${active === item.key ? 'active' : ''}`} onClick={() => navigate(item.path)}><Icon name={item.icon} /><Text>{item.label}</Text></Button>)}
        <View className='sidebar-footer'><Text className='tiny-label'>每一步，都有迹可循</Text><Text className='muted'>学习 / 练习 / 再理解</Text></View>
      </View>}
      <View className='studio-main'>
        <View className='page-heading'><Text className='page-title'>{title}</Text>{subtitle && <Text className='page-subtitle'>{subtitle}</Text>}</View>
        {!guest && !appearance && reserved && shown && <View className={`companion-reserved pose-${portrait.pose} ${portrait.enabled ? 'companion-animated' : ''}`}>
          <View className='actions'><Button className='text-button' onClick={() => Taro.navigateTo({ url: `/learning/companion/index?character=${settings.companionForm}` })}><Icon name='chat' size={16} />伙伴对话</Button>{focus && <Button className='text-button' onClick={() => { setDetached(true); settings.update({ companionFolded: false }) }}>自由移动</Button>}</View>
          <Image className='companion-portrait' src={portrait.source} mode='aspectFit' onClick={portrait.nextPose} />
        </View>}
        {children}
      </View>
    </View>
    {!guest && <View className='mobile-navigation'>{navigation.map(item => <Button key={item.key} className={`mobile-nav-item ${active === item.key ? 'active' : ''}`} onClick={() => navigate(item.path)}><Icon name={item.icon} /><Text>{item.label}</Text></Button>)}</View>}
    {floating && !guest && !appearance && <Companion layout={children} reducedMotion={settings.reducedMotion} onSafeChange={setFloatingSafe} onHide={() => settings.update({ companionFolded: true })} />}
    {appearance && <View className='modal-backdrop' onClick={() => setAppearance(false)}><View className='appearance-dialog' onClick={event => event.stopPropagation()}>
      <View className='section-heading'><Text className='section-title'>我的学园外观</Text><Button className='icon-button' aria-label='关闭外观设置' onClick={() => setAppearance(false)}><Icon name='close' /></Button></View>
      <View className='theme-options'>{themes.map(theme => <Button key={theme.id} className={`theme-option ${settings.theme === theme.id ? 'selected' : ''}`} onClick={() => settings.update({ theme: theme.id })}>
        <View className='theme-swatch' style={{ background: theme.paper, borderColor: theme.accent }}><View style={{ background: theme.accent }} /></View><View><Text>{theme.name}</Text><Text className='muted'>{theme.motif}</Text></View>{settings.theme === theme.id && <Icon name='check' />}
      </Button>)}</View>
      <View className='setting-row'><Text>学习伙伴</Text><Switch checked={settings.companion} onChange={e => settings.update({ companion: e.detail.value })} /></View>
      {!guest && <Button className='secondary-button' onClick={() => { setAppearance(false); Taro.navigateTo({ url: `/learning/companion/index?character=${settings.companionForm}` }) }}><Icon name='chat' size={18} />伙伴对话</Button>}
      <View className='setting-row'><Text>伙伴形态</Text><View className='actions'><Button className={`form-swatch pink ${settings.companionForm === 'pink' ? 'selected' : ''}`} aria-label='粉樱学妹' onClick={() => settings.update({ companionForm: 'pink' })} /><Button className={`form-swatch orange ${settings.companionForm === 'orange' ? 'selected' : ''}`} aria-label='橘晴学妹' onClick={() => settings.update({ companionForm: 'orange' })} /></View></View>
      <View className='pose-selector'>{(['auto','read','wave','celebrate'] as const).map((pose, index) => <Button key={pose} className={settings.companionPose === pose ? 'active' : ''} onClick={() => settings.update({ companionPose: pose })}>{['自动','阅读 / 思考','招手','庆祝'][index]}</Button>)}</View>
      <View className='setting-row'><Text>减少动效</Text><Switch checked={settings.reducedMotion} onChange={e => settings.update({ reducedMotion: e.detail.value })} /></View>
    </View></View>}
  </View>
}

export function Notice({ message, retry }: { message: string; retry?: () => void }) {
  return <View className='notice' role='alert'><Text>{message}</Text>{retry && <Button className='text-button' onClick={retry}><Icon name='refresh' size={16} />重试</Button>}</View>
}

export function Empty({ title, text }: { title: string; text: string }) {
  return <View className='empty-state'><View className='empty-icon'><Icon name='book' size={30} /></View><Text className='section-title'>{title}</Text><Text className='muted'>{text}</Text></View>
}
