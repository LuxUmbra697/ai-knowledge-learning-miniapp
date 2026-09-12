import { Image } from '@tarojs/components'

const icons: Record<string, string> = {
  book: require('../assets/icons/book-open.png'),
  home: require('../assets/icons/house.png'),
  library: require('../assets/icons/library.png'),
  chat: require('../assets/icons/messages-square.png'),
  review: require('../assets/icons/calendar-check.png'),
  report: require('../assets/icons/chart-no-axes-combined.png'),
  user: require('../assets/icons/user-round.png'),
  settings: require('../assets/icons/settings-2.png'),
  arrow: require('../assets/icons/arrow-up-right.png'),
  upload: require('../assets/icons/upload.png'),
  close: require('../assets/icons/x.png'),
  logout: require('../assets/icons/log-out.png'),
  check: require('../assets/icons/check.png'),
  refresh: require('../assets/icons/rotate-cw.png'),
  clock: require('../assets/icons/clock-3.png'),
  sparkle: require('../assets/icons/sparkles.png'),
}

export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  return <Image className='studio-icon' src={icons[name] || icons.book} style={{ width: `${size}px`, height: `${size}px` }} mode='aspectFit' />
}
