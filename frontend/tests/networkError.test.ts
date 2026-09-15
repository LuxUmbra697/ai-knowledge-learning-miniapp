import test from 'node:test'
import assert from 'node:assert/strict'
import { networkErrorMessage } from '../src/services/networkError'

test('WeChat domain allowlist failures explain configuration instead of claiming an offline network', () => {
  assert.equal(networkErrorMessage({ errMsg: 'request:fail url not in domain list' }), '小程序服务器域名未配置，请管理员在微信公众平台添加合法域名后重试')
})

test('timeouts, TLS failures and cancellation have distinct safe feedback', () => {
  assert.equal(networkErrorMessage({ errMsg: 'request:fail timeout' }), '连接超时，请稍后重试')
  assert.equal(networkErrorMessage({ errMsg: 'request:fail ssl hand shake error' }), 'HTTPS 安全连接失败，请检查网络或联系管理员')
  assert.equal(networkErrorMessage({ errMsg: 'request:fail abort' }), '请求已取消')
  for (const reason of [null, 'private provider key', { errMsg: 'private account token' }, { errMsg: 123 }]) {
    assert.equal(networkErrorMessage(reason), '网络暂不可用，请检查连接后重试')
  }
})
