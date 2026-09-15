export function networkErrorMessage(reason: unknown): string {
  const value = reason && typeof reason === 'object' ? (reason as { errMsg?: unknown }).errMsg : ''
  const message = typeof value === 'string' ? value.toLowerCase() : ''
  if (message.includes('url not in domain list') || message.includes('not in domain list')) {
    return '小程序服务器域名未配置，请管理员在微信公众平台添加合法域名后重试'
  }
  if (message.includes('timeout') || message.includes('timed out')) return '连接超时，请稍后重试'
  if (/ssl|certificate|tls|handshake|hand shake/.test(message)) return 'HTTPS 安全连接失败，请检查网络或联系管理员'
  if (message.includes('abort')) return '请求已取消'
  return '网络暂不可用，请检查连接后重试'
}
