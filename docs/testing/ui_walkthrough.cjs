/* Scripted browser test of the EcoMesh website (Phase IV, P2 functional testing).
 *
 * Drives a real Chrome against a running server and records pass/fail per check
 * in docs/testing/results/ui_walkthrough.json.
 *
 *   python -m api.server                       # terminal 1 (serves the built UI)
 *   npm install --no-save puppeteer-core       # once, anywhere on NODE_PATH
 *   node docs/testing/ui_walkthrough.cjs [http://127.0.0.1:8000]
 *
 * Set CHROME to the browser path if Chrome is not in the default location.
 */
const fs = require('fs')
const path = require('path')
const puppeteer = require('puppeteer-core')

const BASE = process.argv[2] || 'http://127.0.0.1:8000'
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const OUT = path.join(__dirname, 'results', 'ui_walkthrough.json')
const wait = (ms) => new Promise((r) => setTimeout(r, ms))

const checks = []
const record = (id, name, passed, detail = '') => {
  checks.push({ id, name, passed: !!passed, detail })
  console.log(`${passed ? 'PASS' : 'FAIL'}  ${id}  ${name}${detail ? '  -  ' + detail : ''}`)
}

;(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
  const page = await browser.newPage()
  const errors = []
  let expect409 = false // UT-12 provokes a 409 on purpose; the browser logs it as a console error
  page.on('console', (m) => {
    if (m.type() !== 'error') return
    if (expect409 && m.text().includes('409')) return
    errors.push(m.text().slice(0, 160))
  })
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
  page.on('dialog', async (d) => { errors.push('dialog: ' + d.message()); await d.dismiss() })
  await page.setViewport({ width: 1440, height: 1000 })

  const api = (method, url, body) =>
    page.evaluate(async (m, u, b) => {
      const r = await fetch(u, { method: m, headers: { 'content-type': 'application/json' }, body: b ? JSON.stringify(b) : undefined })
      return { status: r.status, body: await r.json() }
    }, method, url, body)
  const text = () => page.evaluate(() => document.getElementById('root').innerText)
  const click = (label) =>
    page.evaluate((t) => {
      const b = [...document.querySelectorAll('button')].find((x) => x.textContent.trim().startsWith(t) && !x.disabled)
      if (b) b.click()
      return !!b
    }, label)
  const settle = async (maxMs = 30000) => {
    const start = Date.now()
    await wait(1000)
    while (Date.now() - start < maxMs && (await page.evaluate(() => [...document.querySelectorAll('button')].some((b) => b.disabled && b.closest('li'))))) await wait(500)
    await wait(600)
  }
  const note = async () => page.evaluate(() => [...document.querySelectorAll('ol li .text-ok')].map((n) => n.textContent.trim()).filter((s) => s.length > 20).slice(-1)[0] || '')

  // ---- UT-01: every page opens from the top menu with no console error
  await page.goto(BASE + '/', { waitUntil: 'networkidle2' })
  await api('POST', '/api/lab/reset', { preset: 'demo5' })
  await wait(7000)
  const nav = ['Live demo', 'Node view', 'Rescue dashboard', 'Simulator', 'Overview']
  let ok = true
  const lens = []
  for (const label of nav) {
    await page.evaluate((t) => [...document.querySelectorAll('header nav a')].find((a) => a.textContent.trim() === t)?.click(), label)
    await wait(1200)
    const n = (await text()).length
    lens.push(n)
    ok = ok && n > 200
  }
  for (const label of ['Routing', 'Reliability', 'Wire protocol', 'Security']) {
    await page.evaluate(() => [...document.querySelectorAll('header nav button')].find((b) => b.textContent.includes('Under the hood'))?.click())
    await wait(300)
    await page.evaluate((t) => [...document.querySelectorAll('header nav a')].find((a) => a.textContent.includes(t))?.click(), label)
    await wait(1200)
    const n = (await text()).length
    lens.push(n)
    ok = ok && n > 200
  }
  record('UT-01', 'All 9 pages open from the top menu and render content', ok, `text length per page: ${lens.join(', ')}`)

  // ---- UT-02/03: long-press SOS button
  await page.goto(BASE + '/node/L1', { waitUntil: 'networkidle2' })
  await wait(1500)
  const before = (await api('GET', '/api/nodes/L1')).body.thread.filter((m) => m.priority === 0).length
  const btn = await page.$('button[aria-label="Hold to send an SOS"]')
  const box = await btn.boundingBox()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down(); await wait(500); await page.mouse.up(); await wait(1500)
  const afterEarly = (await api('GET', '/api/nodes/L1')).body.thread.filter((m) => m.priority === 0).length
  record('UT-02', 'Releasing the SOS button early (0.5 s) does not send an SOS', afterEarly === before, `SOS count ${before} -> ${afterEarly}`)
  await page.mouse.down(); await wait(1800); await page.mouse.up(); await wait(3500)
  const view = (await api('GET', '/api/nodes/L1')).body
  const sos = view.thread.filter((m) => m.priority === 0)
  record('UT-03', 'Holding the SOS button for 1.8 s sends an SOS that is delivered', sos.length === before + 1 && sos[sos.length - 1].status === 'delivered', `last SOS status: ${sos.length ? sos[sos.length - 1].status : 'none'}`)

  // ---- UT-04..09: the six demo beats, driven by the on-screen buttons
  await api('POST', '/api/lab/reset', { preset: 'demo5' })
  await wait(7000)
  await page.goto(BASE + '/demo', { waitUntil: 'networkidle2' })
  await wait(1500)
  const beats = [
    ['UT-04', 'Beat 1: self-organisation (all nodes know the whole mesh)', 'Check convergence', /know all 5/],
    ['UT-05', 'Beat 2: an SOS sent last still arrives first', 'Send 6 routine', /arrived first/],
    ['UT-06', 'Beat 3: kill the relay on the active path, next SOS reroutes', 'Kill the relay', /still arrived via/],
    ['UT-07', 'Beat 4: gateway down, 5 SOS held in store-and-forward', 'Kill the gateway', /5 SOS messages are being held/],
    ['UT-08', 'Beat 5: gateway back, all held SOS flush', 'Bring the gateway back', /5 of 5 held messages flushed/],
  ]
  for (const [id, name, label, re] of beats) {
    const clicked = await click(label)
    await settle()
    const msg = await note()
    record(id, name, clicked && re.test(msg), msg)
  }
  const sim = await click('Open the simulator')
  await wait(1500)
  record('UT-09', 'Beat 6 opens the simulator page', sim && page.url().endsWith('/simulator'), page.url())

  // ---- UT-10: the layouts
  const layouts = { demo5: 5, building12: 13, collapse20: 21, chain6: 6, blank: 0 }
  let layoutsOk = true
  const seen = []
  for (const [p, n] of Object.entries(layouts)) {
    const r = await api('POST', '/api/lab/reset', { preset: p })
    seen.push(`${p}:${r.body.nodes ? r.body.nodes.length : r.status}`)
    layoutsOk = layoutsOk && r.body.nodes && r.body.nodes.length === n
  }
  record('UT-10', 'All 5 mesh layouts load with the expected node counts', layoutsOk, seen.join(', '))
  await api('POST', '/api/lab/reset', { preset: 'demo5' })
  await wait(7000)

  // ---- UT-11: a switched-off node
  await api('POST', '/api/lab/nodes/L3/kill')
  await page.goto(BASE + '/node/L3', { waitUntil: 'networkidle2' })
  await wait(1500)
  const offText = await text()
  record('UT-11', 'A switched-off node shows "This phone is off" and cannot send', offText.includes('This phone is off'))
  expect409 = true
  const blocked = await api('POST', '/api/nodes/L3/sos')
  await wait(300)
  expect409 = false
  record('UT-12', 'The API refuses an SOS from a switched-off node (HTTP 409)', blocked.status === 409, `status ${blocked.status}`)
  await api('POST', '/api/lab/nodes/L3/revive')

  // ---- UT-13: security drill
  await page.goto(BASE + '/security', { waitUntil: 'networkidle2' })
  await wait(800)
  await click('Run the drill')
  await wait(5000)
  const drill = await text()
  const defended = (drill.match(/B dropped it/g) || []).length
  record('UT-13', 'Security drill: honest relay accepted, 3 attacks rejected', drill.includes('B accepted and decrypted it') && defended === 3, `${defended} attacks rejected`)

  // ---- UT-14: simulator page runs a scenario in the worker pool
  await page.goto(BASE + '/simulator', { waitUntil: 'networkidle2' })
  await wait(800)
  await click('Run 6 simulations')
  await wait(9000)
  const simText = await text()
  const w = (simText.match(/WEIGHTED \(DIJKSTRA\)\s*([\d.]+)%/i) || [])[1]
  const h = (simText.match(/HOP-COUNT ROUTING\s*([\d.]+)%/i) || [])[1]
  record('UT-14', 'Simulator page: weighted routing beats hop-count on the same seeds', w && h && Number(w) > Number(h), `weighted ${w}% vs hop-count ${h}%`)

  // ---- UT-15: phone width, no sideways scroll
  await page.setViewport({ width: 390, height: 844, isMobile: true })
  const over = []
  for (const p of ['', 'demo', 'node', 'rescue', 'routing', 'reliability', 'protocol', 'security', 'simulator']) {
    await page.goto(`${BASE}/${p}`, { waitUntil: 'networkidle2' })
    await wait(700)
    over.push(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth))
  }
  record('UT-15', 'At 390 px width no page scrolls sideways', over.every((x) => x <= 0), `overflow px per page: ${over.join(', ')}`)

  record('UT-16', 'No console errors or script exceptions during the whole run', errors.length === 0, errors.length ? [...new Set(errors)].join(' | ') : 'none')

  await browser.close()
  fs.mkdirSync(path.dirname(OUT), { recursive: true })
  fs.writeFileSync(OUT, JSON.stringify({ date: new Date().toISOString(), base: BASE, checks }, null, 2))
  const failed = checks.filter((c) => !c.passed).length
  console.log(`\n${checks.length - failed}/${checks.length} checks passed -> ${path.relative(process.cwd(), OUT)}`)
  process.exit(failed ? 1 : 0)
})().catch((e) => { console.error(e); process.exit(2) })
