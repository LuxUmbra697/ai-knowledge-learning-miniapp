import Taro from '@tarojs/taro'
export async function needsDocumentPrivacy() {
  if (typeof Taro.getPrivacySetting !== 'function') return false
  const privacy = await new Promise<Taro.getPrivacySetting.SuccessCallbackResult>((resolve, reject) => Taro.getPrivacySetting({ success: resolve, fail: reject }))
  return privacy.needAuthorization
}
export async function chooseDocument() {
  const result = await Taro.chooseMessageFile({ count: 1, type: 'file', extension: ['pdf', 'docx', 'txt', 'md'] })
  const file = result.tempFiles[0]
  return file ? { ...file, release: () => {} } : null
}
