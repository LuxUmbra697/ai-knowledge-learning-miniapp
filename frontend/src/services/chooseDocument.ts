import Taro from '@tarojs/taro'
export async function chooseDocument() {
  const result = await Taro.chooseMessageFile({ count: 1, type: 'file', extension: ['pdf', 'docx', 'txt', 'md'] })
  const file = result.tempFiles[0]
  return file ? { ...file, release: () => {} } : null
}
