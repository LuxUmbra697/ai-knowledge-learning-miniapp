import Taro from '@tarojs/taro'

export async function qrImage(source: string) {
  const match = /^data:image\/(png|jpeg);base64,([A-Za-z0-9+/=]+)$/.exec(source)
  if (!match) throw new Error('二维码图片格式不正确')
  const manager = Taro.getFileSystemManager()
  const path = `${Taro.env.USER_DATA_PATH}/ai-learn-qr-${Date.now()}.${match[1]}`
  await new Promise<void>((resolve, reject) => manager.writeFile({ filePath: path, data: match[2], encoding: 'base64', success: () => resolve(), fail: reject }))
  return { source: path, release: () => manager.unlink({ filePath: path, fail: () => {} }) }
}
