import fs from 'node:fs/promises'
import path from 'node:path'
import sharp from 'sharp'

const root = path.resolve(import.meta.dirname, '..')
const names = ['book-open','house','library','messages-square','calendar-check','chart-no-axes-combined','user-round','settings-2','arrow-up-right','upload','x','log-out','check','rotate-cw','clock-3','sparkles','plus','trash-2','share-2','ellipsis']
await fs.mkdir(path.join(root, 'src/assets/icons'), { recursive: true })
for (const name of names) {
  const file = path.join(root, 'node_modules/lucide-static/icons', `${name}.svg`)
  const svg = (await fs.readFile(file, 'utf8')).replaceAll('currentColor', '#364c45')
  await sharp(Buffer.from(svg)).resize(48, 48).png().toFile(path.join(root, 'src/assets/icons', `${name}.png`))
}
const arguments_ = process.argv.slice(2)
for (const form of ['pink', 'orange']) {
  const index = arguments_.indexOf(`--${form}`)
  if (index < 0) continue
  const source = arguments_[index + 1]
  const metadata = await sharp(source).metadata()
  if (!metadata.hasAlpha || metadata.width % 3 !== 0) throw new Error('Expected transparent three-column atlas')
  const width = metadata.width / 3
  for (let pose = 0; pose < 3; pose++) {
    await sharp(source).extract({ left: pose * width, top: 0, width, height: metadata.height })
      .resize({ height: 360 }).png({ palette: true, quality: 90, compressionLevel: 9 })
      .toFile(path.join(root, 'src/assets', `companion-${form}-${pose}.png`))
  }
}
console.log('Lucide icons and supplied companion frames prepared.')
