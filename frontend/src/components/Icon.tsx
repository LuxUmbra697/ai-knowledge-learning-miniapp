import { Image } from '@tarojs/components'
import { assetUrl } from '../services/assets'

const icons: Record<string, string> = {
  book: assetUrl('icons/book-open.png'),
  home: assetUrl('icons/house.png'),
  library: assetUrl('icons/library.png'),
  chat: assetUrl('icons/messages-square.png'),
  review: assetUrl('icons/calendar-check.png'),
  report: assetUrl('icons/chart-no-axes-combined.png'),
  user: assetUrl('icons/user-round.png'),
  settings: assetUrl('icons/settings-2.png'),
  arrow: assetUrl('icons/arrow-up-right.png'),
  upload: assetUrl('icons/upload.png'),
  close: assetUrl('icons/x.png'),
  logout: assetUrl('icons/log-out.png'),
  check: assetUrl('icons/check.png'),
  refresh: assetUrl('icons/rotate-cw.png'),
  clock: assetUrl('icons/clock-3.png'),
  sparkle: assetUrl('icons/sparkles.png'),
  add: assetUrl('icons/plus.png'),
  trash: assetUrl('icons/trash-2.png'),
  share: assetUrl('icons/share-2.png'),
  more: assetUrl('icons/ellipsis.png'),
}

export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  return <Image className='studio-icon' src={icons[name] || icons.book} style={{ width: `${size}px`, height: `${size}px` }} mode='aspectFit' />
}
