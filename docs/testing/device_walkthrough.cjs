/* Scripted browser test of the EcoMesh DEVICE screens (the one app, story/node.html).
 *
 * It starts the five devices itself (python -m story.local), opens the survivor phone
 * (port 8101), a second phone (8103), the gateway (8104) and the rescue console (8105)
 * in real Chrome windows, drives them the way a user would, and records pass or fail
 * for every check in docs/testing/results/device_walkthrough.json.
 *
 *   npm install --no-save puppeteer-core        # once, anywhere on NODE_PATH
 *   node docs/testing/device_walkthrough.cjs            # starts and stops the devices itself
 *   node docs/testing/device_walkthrough.cjs --no-spawn # use devices that are already running
 *
 * Set CHROME if Chrome is not in the default location, PYTHON for another interpreter.
 */
const fs = require('fs')
const path = require('path')
const { spawn, execSync } = require('child_process')
const puppeteer = require('puppeteer-core')

const ROOT = path.resolve(__dirname, '..', '..')
const OUT = path.join(__dirname, 'results', 'device_walkthrough.json')
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const PYTHON = process.env.PYTHON || 'python'
const SPAWN = !process.argv.includes('--no-spawn')
const URL = (port) => `http://127.0.0.1:${port}`
const P = { survivor: 8101, phone3: 8103, gateway: 8104, rescue: 8105 }

const wait = (ms) => new Promise((r) => setTimeout(r, ms))
const checks = []
const record = (id, name, passed, detail = '') => {
  checks.push({ id, name, passed: !!passed, detail: String(detail).slice(0, 220) })
  console.log(`${passed ? 'PASS' : 'FAIL'}  ${id}  ${name}${detail ? '  -  ' + String(detail).slice(0, 160) : ''}`)
}

async function until(fn, timeout = 20000, step = 400) {
  const end = Date.now() + timeout
  let last
  while (Date.now() < end) {
    try { last = await fn(); if (last) return last } catch (e) { last = false }
    await wait(step)
  }
  return false
}

async function main() {
  let devices = null
  if (SPAWN) {
    devices = spawn(PYTHON, ['-m', 'story.local', '--no-browser'], { cwd: ROOT, stdio: 'ignore', windowsHide: true })
  }
  const stopDevices = () => {
    if (!devices) return
    try {
      if (process.platform === 'win32') execSync(`taskkill /PID ${devices.pid} /T /F`, { stdio: 'ignore' })
      else devices.kill('SIGTERM')
    } catch { /* already gone */ }
  }
  process.on('exit', stopDevices)

  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', protocolTimeout: 120000,
    args: ['--no-sandbox', '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows'] })
  const errors = []
  const open = async (port, width = 1000, height = 2200) => {
    const page = await browser.newPage()
    page.on('console', (m) => {
      if (m.type() !== 'error') return
      if ((m.location().url || '').includes('favicon')) return
      errors.push(`${port}: ${m.text().slice(0, 140)}`)
    })
    page.on('pageerror', (e) => errors.push(`${port}: pageerror ${e.message}`))
    await page.setViewport({ width, height })
    // the devices need a few seconds to start listening
    const ok = await until(async () => { try { await page.goto(URL(port), { waitUntil: 'domcontentloaded' }); return true } catch { return false } }, 40000, 800)
    if (!ok) throw new Error('device on port ' + port + ' did not start')
    return page
  }
  const front = async (page) => { await page.bringToFront(); await wait(200) }
  const text = (page, sel) => page.evaluate((s) => (document.querySelector(s) || {}).innerText || '', sel)
  const hold = async (page, ms) => {
    await front(page)
    const box = await (await page.$('#sosBtn')).boundingBox()
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await page.mouse.down(); await wait(ms); await page.mouse.up()
  }
  const sentCount = (page) => page.evaluate(async () => (await (await fetch('/api/me')).json()).thread.filter((m) => m.direction === 'sent').length)
  const clickText = async (page, sel, label) => {
    await front(page)
    return page.evaluate((s, t) => { const b = [...document.querySelectorAll(s)].find((x) => x.textContent.trim().startsWith(t)); if (b) b.click(); return !!b }, sel, label)
  }

  const survivor = await open(P.survivor)
  const rescue = await open(P.rescue, 1280, 1500)
  const gateway = await open(P.gateway)
  const phone3 = await open(P.phone3)

  // DT-01 / DT-02 the screens load and name their device
  const who1 = [await text(survivor, '#whoName'), await text(survivor, '#whoRole')]
  record('DT-01', 'Survivor screen loads and the app bar names the device', await until(async () => (await text(survivor, '#whoName')) === 'Trapped person'), `${who1.join(' / ')}`)
  const who5 = [await text(rescue, '#whoName'), await text(rescue, '#whoRole')]
  const consoleShown = await rescue.evaluate(() => !document.getElementById('console').hidden && document.getElementById('phone').hidden)
  record('DT-02', 'Rescue device shows the console, with its name in the app bar', who5[0] === 'Rescue team' && consoleShown, `${who5.join(' / ')}`)

  // DT-03 the mesh finds itself
  const connected = await until(async () => (await text(survivor, '#pStatus')).includes('Connected to the rescue team'), 60000)
  const route = await text(survivor, '#pRoute')
  record('DT-03', 'The mesh organises itself: the survivor is connected to the rescue team through phones in between', connected, route.replace(/\s+/g, ' '))

  // DT-04 a short press does not send
  const before = await sentCount(survivor)
  await hold(survivor, 400)
  await wait(1500)
  record('DT-04', 'Releasing the SOS button after 0.4 s sends nothing', (await sentCount(survivor)) === before, `sent messages ${before} -> ${await sentCount(survivor)}`)

  // DT-05 SOS with need and location reaches the console with its route
  await clickText(survivor, '.need', 'Trapped')
  await survivor.type('#where', '3rd floor, room 304')
  await hold(survivor, 1500)
  const arrived = await until(async () => {
    const t = await text(rescue, '#sosList')
    return t.includes('Trapped') && t.includes('3rd floor, room 304') && t.includes('Rescue team') ? t : false
  }, 30000)
  const chips = await rescue.evaluate(() => [...document.querySelectorAll('#sosList .req .rc')].map((e) => e.textContent).join(' > '))
  record('DT-05', 'A held SOS with need and location reaches the rescue console with the route it took', arrived && chips.includes('Trapped person') && chips.includes('Rescue team'), chips)
  const tracker = await until(async () => (await text(survivor, '#pTracker')).includes('The rescue team has your request'), 20000)
  record('DT-06', 'The survivor screen confirms "The rescue team has your request"', tracker)

  // DT-07 "I am safe" appears under Marked safe, not in the requests
  await front(phone3)
  await phone3.click('#safeBtn')
  const safeShown = await until(async () => { const t = await text(rescue, '#cSafe'); return t.includes('Phone 3') && t.includes('SAFE') }, 30000)
  const reqText = await text(rescue, '#sosList')
  record('DT-07', '"I am safe" from another phone appears under Marked safe, not among the requests', safeShown && !reqText.includes('Phone 3'), (await text(rescue, '#cSafe')).replace(/\s+/g, ' ').slice(0, 100))

  // DT-08 a typed message is delivered
  await front(survivor)
  await survivor.click('#pSend summary')
  await survivor.select('#sendTo', 'L5')
  await survivor.type('#sendText', 'Water is rising on floor 2')
  await survivor.click('#sendBtn')
  const msgArrived = await until(async () => (await text(rescue, '#sosList')).includes('Water is rising on floor 2'), 30000)
  record('DT-08', 'A typed message sent to the rescue team is delivered and listed on the console', msgArrived)

  // DT-09 reply: quick reply reaches the survivor
  await front(rescue)
  const replyOpened = await rescue.evaluate(() => { const card = [...document.querySelectorAll('#sosList .req')].find((r) => r.textContent.includes('3rd floor')); const b = card && card.querySelector('[data-reply]'); if (b) b.click(); return !!b })
  await wait(900)
  const quickClicked = await clickText(rescue, '[data-quick]', 'Help is on the way')
  const gotQuick = await until(async () => (await text(survivor, '#pReply')).includes('Help is on the way'), 30000)
  record('DT-09', 'Reply opens and a quick reply "Help is on the way" reaches the survivor', replyOpened && quickClicked && gotQuick, (await text(survivor, '#pReply')).replace(/\s+/g, ' ').slice(0, 90))

  // DT-10 a typed reply survives the 0.7 s refresh and is delivered
  await front(rescue)
  const typed = 'Stay where you are, medics are coming'
  await rescue.evaluate(() => { const ta = document.querySelector('#sosList textarea[data-key^="reply-"]'); if (ta) ta.scrollIntoView({ block: 'center' }) })
  await rescue.click('#sosList textarea[data-key^="reply-"]')
  await rescue.type('#sosList textarea[data-key^="reply-"]', typed)
  await wait(3200) // more than four refreshes
  const kept = await rescue.evaluate(() => { const ta = document.querySelector('#sosList textarea[data-key^="reply-"]'); return ta ? { value: ta.value, focused: document.activeElement === ta } : null })
  await rescue.evaluate(() => document.querySelector('#sosList [data-sendreply]').click())
  const gotTyped = await until(async () => (await text(survivor, '#pReply')).includes(typed), 30000)
  record('DT-10', 'A typed reply survives the 0.7 s refresh (text and focus kept) and reaches the survivor', kept && kept.value === typed && kept.focused && gotTyped, kept ? `kept="${kept.value.slice(0, 30)}..." focused=${kept.focused}` : 'textarea disappeared')

  // DT-11 console filters
  await front(rescue)
  await rescue.evaluate(() => window.scrollTo(0, 0))
  const reqTags = () => rescue.evaluate(() => [...document.querySelectorAll('#sosList .req')].map((r) => (r.querySelector('.tag:not(.new)') || {}).textContent))
  await rescue.click('#fKind [data-kind="SOS"]'); await wait(500)
  const onlySos = await reqTags()
  await rescue.click('#fKind [data-kind="NORMAL"]'); await wait(500)
  const onlyMsg = await reqTags()
  await rescue.click('#fKind [data-kind="all"]'); await wait(500)
  await rescue.select('#fNeed', 'Trapped'); await wait(500)
  const byNeed = await rescue.evaluate(() => [...document.querySelectorAll('#sosList .req .body')].map((e) => e.textContent))
  await rescue.select('#fNeed', 'all'); await wait(300)
  record('DT-11', 'Console filters: SOS only, Messages only, and by need', onlySos.length > 0 && onlySos.every((t) => t === 'SOS') && onlyMsg.length > 0 && onlyMsg.every((t) => t !== 'SOS') && byNeed.length > 0 && byNeed.every((t) => t === 'Trapped'),
         `SOS=${onlySos}; Messages=${onlyMsg}; need=${byNeed}`)

  // DT-12 history filter and CSV export
  await front(rescue)
  await rescue.click('#cHistBox summary')
  await until(async () => (await rescue.evaluate(() => document.querySelectorAll('#cHList li').length)) > 0, 15000)
  await rescue.select('#cHKind', 'SOS'); await wait(1200)
  const hist = await rescue.evaluate(() => [...document.querySelectorAll('#cHList li')].map((l) => l.textContent))
  const csv = await rescue.evaluate(async () => { const r = await fetch('/api/export.csv'); return { status: r.status, type: r.headers.get('content-type'), body: await r.text() } })
  const csvLines = csv.body.trim().split(/\r?\n/)
  const csvButton = await rescue.evaluate(() => !document.getElementById('csvBtn').hidden)
  record('DT-12', 'History filter shows only the chosen priority; the CSV button is shown and the export has a header and rows',
         hist.length > 0 && hist.every((t) => t.includes('SOS')) && csvButton && csv.status === 200 && csvLines.length >= 2 && /time|from/i.test(csvLines[0]),
         `history=${hist.length} SOS rows; csv ${csv.status} ${csv.type}; header: ${csvLines[0]}; rows: ${csvLines.length - 1}`)

  // DT-13 activity panel
  const act = await survivor.evaluate(() => [...document.querySelectorAll('#pActivity li')].map((l) => l.textContent.replace(/\s+/g, ' ').trim()))
  record('DT-13', 'The "What this device is doing" panel lists live events in plain language', act.length >= 3 && act.some((t) => /hear|route|message/i.test(t)), act.slice(0, 3).join(' | '))

  // DT-14 gateway view
  const gwBanner = await text(gateway, '#pStatus')
  const gwHelping = await gateway.evaluate(() => !document.getElementById('pHelping').hidden)
  record('DT-14', 'The gateway view says it is online and shows the messages it passed on', gwBanner.includes('Gateway online') && gwHelping, gwBanner.replace(/\s+/g, ' ').slice(0, 70))

  // DT-15 / DT-16 gateway switched off: the SOS is held; switched on: it is delivered
  await front(gateway)
  await gateway.evaluate(() => [...document.querySelectorAll('summary')].find((s) => s.textContent.includes('Demonstration')).click())
  await gateway.evaluate(() => document.querySelector('.powerBtn').click())
  const lost = await until(async () => (await text(survivor, '#pStatus')).includes('Searching for a path'), 60000)
  await front(survivor)
  await survivor.evaluate(() => window.scrollTo(0, 0))
  await survivor.evaluate(() => { document.getElementById('where').value = '' })
  await survivor.type('#where', 'Stairwell B')
  await hold(survivor, 1500)
  const heldShown = await until(async () => (await text(survivor, '#pTracker')).includes('Saved, waiting for a path'), 20000)
  record('DT-15', 'With the gateway off, an SOS shows "Saved, waiting for a path"', lost && heldShown, `lost route: ${lost}`)
  await front(gateway)
  await gateway.evaluate(() => document.querySelector('.powerBtn').click())
  const flushed = await until(async () => (await text(survivor, '#pTracker')).includes('The rescue team has your request'), 90000)
  const stairs = await until(async () => (await text(rescue, '#sosList')).includes('Stairwell B'), 20000)
  record('DT-16', 'With the gateway back on, the held SOS is delivered and appears on the console', flushed && stairs)

  // DT-17 narrow screens
  const narrow = []
  for (const [page, port] of [[survivor, P.survivor], [rescue, P.rescue]]) {
    for (const w of [390, 320]) {
      await page.setViewport({ width: w, height: 900 })
      await wait(500)
      narrow.push(`${port}@${w}:${await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)}`)
    }
  }
  record('DT-17', 'At 390 px and 320 px wide neither screen scrolls sideways', narrow.every((s) => Number(s.split(':')[1]) <= 0), narrow.join(', '))

  record('DT-18', 'No script errors or console errors on any device screen during the run', errors.length === 0, errors.length ? [...new Set(errors)].join(' | ') : 'none')

  await browser.close()
  stopDevices()
  fs.mkdirSync(path.dirname(OUT), { recursive: true })
  fs.writeFileSync(OUT, JSON.stringify({ date: new Date().toISOString(), devices: 'python -m story.local (5 processes)', checks }, null, 2))
  const failed = checks.filter((c) => !c.passed).length
  console.log(`\n${checks.length - failed}/${checks.length} checks passed -> ${path.relative(process.cwd(), OUT)}`)
  process.exit(failed ? 1 : 0)
}

main().catch((e) => { console.error(e); process.exit(2) })
