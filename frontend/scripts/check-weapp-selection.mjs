import assert from 'node:assert/strict'
import automator from 'miniprogram-automator'

const endpoint = process.env.WEAPP_AUTOMATION_ENDPOINT || 'ws://127.0.0.1:9420'
assert.equal(new URL(endpoint).hostname, '127.0.0.1', 'Use a local DevTools automation endpoint')
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))
const timeout = setTimeout(() => { console.error('Native selection check timed out'); process.exit(1) }, 60000)
let mini
try {
  mini = await automator.connect({ wsEndpoint: endpoint })
  const account = await mini.callWxMethod('getAccountInfoSync')
  assert.equal(account.miniProgram.appId, 'wx7abde39fb8222887')
  await mini.reLaunch('/learning/companion/index?character=pink')
  for (const [character, name, select] of [['pink', '樱野小满', -1], ['orange', '秋庭澄', 1], ['pink', '樱野小满', 0]]) {
    let page = await mini.currentPage()
    if (select >= 0) await (await page.$$('.room-character-tabs button'))[select].tap()
    let matched = false
    for (let attempt = 0; attempt < 30; attempt++) {
      await wait(200)
      page = await mini.currentPage()
      assert.equal(page.path, 'learning/companion/index', 'Sign in with WeChat before running this check')
      const room = await page.$('.room-name'), portrait = await page.$('.companion-dock image')
      if (room && portrait && await room.text() === name && (await portrait.attribute('src')).includes(`companion-${character}-`)) {
        matched = true
        break
      }
    }
    assert.ok(matched, `One selection must update the ${character} room and header without another tap`)
  }
  console.log(JSON.stringify({ appid: account.miniProgram.appId, single_tap_round_trip: true,
    header_matches_body: true, paid_calls: 0, physical_device: false }))
} finally {
  mini?.disconnect()
  clearTimeout(timeout)
}
