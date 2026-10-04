import { chromium } from 'playwright'
const OUT = new URL('./shots', import.meta.url).pathname
const BASE = 'http://localhost:3199/vi/prototype-backoffice-shell'
const browser = await chromium.launch({ channel: 'chrome' })
const cases = [
  { name: '320x640-200pct', vp: { width: 320, height: 640 }, root: '32px' },
  { name: '1280x800-100pct', vp: { width: 1280, height: 800 }, root: null },
  { name: '1280x800-200pct', vp: { width: 1280, height: 800 }, root: '32px' },
]
for (const c of cases) {
  for (const v of ['now', 'A', 'B', 'C']) {
    const page = await browser.newPage({ viewport: c.vp })
    await page.goto(`${BASE}?variant=${v}`)
    await page.waitForSelector('main h1')
    await page.addStyleTag({ content: '[data-prototype-switcher]{display:none!important}' })
    if (c.root) await page.addStyleTag({ content: `:root { font-size: ${c.root}; }` })
    await page.evaluate(() => document.fonts.ready)
    await page.waitForTimeout(300)
    const m = await page.evaluate(() => {
      const r = (el) => { if (!el) return null; const b = el.getBoundingClientRect(); return { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height) } }
      const main = document.querySelector('main'); const h1 = document.querySelector('main h1')
      const vis = [...document.querySelectorAll('aside, header')].filter(e => getComputedStyle(e).display !== 'none')
      return { main: r(main), h1: r(h1), mainScrollW: main.scrollWidth, mainClientW: main.clientWidth,
        chrome: vis.map(e => ({ tag: e.tagName, ...r(e) })),
        doc: { sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth } }
    })
    console.log(c.name, v, JSON.stringify(m))
    await page.screenshot({ path: `${OUT}/${c.name}-${v}.png`, fullPage: c.vp.width === 320 })
    if (v === 'A' && c.vp.width === 320) {
      await page.getByRole('button', { name: 'Mở menu điều hướng' }).click()
      await page.waitForTimeout(400)
      const d = await page.evaluate(() => { const el = document.querySelector('[role=dialog]'); const b = el.getBoundingClientRect(); return { w: Math.round(b.width), sw: el.scrollWidth, cw: el.clientWidth } })
      console.log(c.name, 'A-drawer-open', JSON.stringify(d))
      await page.screenshot({ path: `${OUT}/${c.name}-A-open.png` })
    }
    await page.close()
  }
}
await browser.close()
