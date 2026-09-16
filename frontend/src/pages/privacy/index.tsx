import { View, Text, Button } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { StudioShell } from '../../components/StudioShell'
import { navigate } from '../../services/access'

const sections = [
  ['浏览与登录', '不登录也能浏览首页和这份说明。账号登录使用你填写的账号、密码与可选昵称；密码经哈希保存。小程序微信登录仅在你点击后交换临时 code，保存用于区分账号的 OpenID。我们不会索取你的手机号、通讯录、位置或微信头像。'],
  ['学习材料与记录', '仅在你主动选择上传文件后读取所选 PDF、DOCX、TXT 或 Markdown。材料正文、索引、作答、错题、复习计划和角色对话按账号保存，用于问答、评分、复习与历史查看，不与其他用户共享。不要上传无权处理的个人信息或涉密材料。'],
  ['模型与存储服务', '使用 AI 功能时，相关问题、选取的材料片段或对话会发送给 DeepSeek、阿里云百炼完成文本、向量或图片处理。学习数据库与私人文件使用腾讯云 MySQL 和 COS；公共界面图片从阿里云 OSS 加载。供应商会接收请求所必需的信息，请在发起前确认材料可用于该处理。'],
  ['网页搜索与伙伴记忆', '网页搜索默认不自动发送私人知识库；仅在你开启网页参考后发送本次公开主题。伙伴记忆按用户与角色隔离，记忆页可查看、修改和删除。关闭伙伴不会自动删除已保存的对话。'],
  ['本机数据与安全', '本机保存登录凭据、外观偏好、伙伴位置和未完成练习状态。退出登录会清除本机登录凭据；修改密码会使旧会话失效。恢复码只展示一次，服务端保存摘要，请勿公开分享。运行诊断使用请求编号与错误类型，不记录密码或模型密钥。'],
  ['管理与联系', '你可以修改昵称、密码，删除知识材料和伙伴记忆，或退出登录。退出不等于删除服务器上的学习记录；当前未提供整账号一键注销。其他数据权利请求请通过小程序资料页公示的运营联系渠道提出并验证身份，不要在公开反馈中提交密码、恢复码或学习材料。'],
]
export default function PrivacyPage() {
  return <StudioShell title='隐私说明' subtitle='更新日期：2026-09-16' compact focus>
    <View className='privacy-content'>{sections.map(([title, copy]) => <View className='privacy-section' key={title}><Text className='section-title'>{title}</Text><Text className='privacy-copy'>{copy}</Text></View>)}</View>
    {process.env.TARO_ENV === 'weapp' && <Button className='text-button' onClick={() => Taro.openPrivacyContract({ fail: () => { void Taro.showToast({ title: '平台隐私指引暂不可用', icon: 'none' }) } })}>查看微信平台隐私指引</Button>}
    <Button className='text-button' onClick={() => navigate('/pages/index/index')}>返回学习首页</Button>
  </StudioShell>
}
