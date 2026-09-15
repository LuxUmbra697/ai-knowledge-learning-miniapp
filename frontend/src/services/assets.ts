export const ASSET_BASE_URL = 'https://ai-knowledge-learn.oss-cn-guangzhou.aliyuncs.com/assets/'

export function assetUrl(relativePath: string): string {
  if (!/^[a-z0-9_-]+(?:\/[a-z0-9_-]+)*\.(?:png|jpg|jpeg|webp)$/.test(relativePath)) {
    throw new Error('Invalid public asset path')
  }
  return ASSET_BASE_URL + relativePath
}

export const companionFrames = {
  pink: [0, 1, 2].map(index => assetUrl(`companion-pink-${index}.png`)),
  orange: [0, 1, 2].map(index => assetUrl(`companion-orange-${index}.png`)),
}
