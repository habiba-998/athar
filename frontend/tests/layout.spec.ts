import { expect, load, test } from './helpers'
import type { Page } from '@playwright/test'

const NAV = ['Dashboard', 'Attack graph', 'Simulation', 'Recommendations', 'Evidence', 'Environment']

async function tab(page: Page, i: number) {
  await page.getByRole('navigation', { name: 'Main' }).locator('button').nth(i).click()
  await page.waitForTimeout(350)
}
const overflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
const x = async (loc: import('@playwright/test').Locator) => (await loc.boundingBox())!.x

for (const [label, width, height] of [['phone 375px', 375, 812], ['phone 390px', 390, 844], ['phone 430px', 430, 932], ['tablet 768px', 768, 1024], ['tablet landscape 1024px', 1024, 768], ['laptop 1280px', 1280, 720], ['desktop 1440px', 1440, 900]] as const) {
  for (const lang of ['en', 'ar'] as const) {
    test(`${label} ${lang}: no page overflow, readable graph, usable controls on every tab`, async ({ page }) => {
      await page.setViewportSize({ width, height })
      await load(page)
      if (lang === 'ar') await page.getByTestId('lang-toggle').click()
      for (const i of NAV.keys()) {
        await tab(page, i)
        expect(await overflow(page), `tab ${NAV[i]}`).toBeLessThanOrEqual(0)
        // touch/click targets: WCAG 2.2 requires at least 24x24 CSS px for pointer targets
        const small = await page.evaluate(() =>
          [...document.querySelectorAll('header button, main button')]
            .filter((b) => { const r = b.getBoundingClientRect(); return r.width > 0 && (r.height < 24 || r.width < 24) })
            .map((b) => (b as HTMLElement).innerText.slice(0, 30)))
        expect(small, `small targets on ${NAV[i]}`).toEqual([])
        if (width <= 430) {
          // bottom navigation: every label fits inside its own button (no collisions, no clipping)
          const clipped = await page.evaluate(() => [...document.querySelectorAll('nav [data-nav-label]')].filter((s) => {
            const b = s.closest('button')!.getBoundingClientRect(), r = s.getBoundingClientRect()
            return r.width > b.width + 0.5 || (s as HTMLElement).scrollWidth > (s as HTMLElement).clientWidth + 1
          }).map((s) => s.textContent))
          expect(clipped, `clipped nav labels on ${NAV[i]}`).toEqual([])
          // phones: comfortable touch targets (44px design target; 40px asserted to allow rounding)
          const tooSmall = await page.evaluate(() =>
            [...document.querySelectorAll('header button, main button, nav button, main select, main input:not([type=checkbox]):not(.sr-only)')]
              .filter((b) => { const r = b.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.height < 40 && !b.classList.contains('sr-only') })
              .map((b) => `${b.tagName}:${((b as HTMLElement).innerText || (b as HTMLElement).getAttribute('aria-label') || '').slice(0, 30)}`))
          expect(tooSmall, `touch targets under 40px on ${NAV[i]}`).toEqual([])
        }
      }
      await tab(page, 1)
      const graph = page.getByTestId('attack-graph')
      const box = (await graph.boundingBox())!
      expect(box.height).toBeGreaterThanOrEqual(300)
      expect(box.width).toBeLessThanOrEqual(width)
      const fontPx = await page.locator('.react-flow__node .font-semibold').first().evaluate((el) => parseFloat(getComputedStyle(el).fontSize))
      expect(fontPx).toBeGreaterThanOrEqual(15)
      await expect(page.locator('.react-flow__node').first()).toBeVisible()
    })
  }
}

test('desktop: choosing a path isolates and frames it at a legible size; the full graph is one click away', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await load(page)
  await tab(page, 1)
  const rendered = () => page.locator('.react-flow__node', { hasText: 'Jump Host' }).locator('.font-semibold').evaluate((el) => parseFloat(getComputedStyle(el).fontSize) * (el.getBoundingClientRect().height / (el as HTMLElement).offsetHeight))
  const overview = await page.locator('.react-flow__node').count()
  expect(overview).toBeGreaterThanOrEqual(15)                                   // no path selected: whole graph
  await page.getByRole('list', { name: 'Attack paths' }).locator('button').nth(1).click()
  const isolate = page.getByLabel('Show only selected path')
  await expect(isolate).toBeChecked()                                           // auto-isolated
  await expect(page.locator('.react-flow__node')).toHaveCount(4)               // Sara, Jump Host, Backup Server, Customer Database
  await page.waitForTimeout(600)
  expect(await rendered()).toBeGreaterThanOrEqual(13)                           // actually rendered size, after zoom
  const box = await page.locator('.react-flow__node', { hasText: 'Customer Database' }).boundingBox()
  const canvas = await page.getByTestId('attack-graph').boundingBox()
  expect(box!.y + box!.height).toBeLessThanOrEqual(canvas!.y + canvas!.height)  // the whole path is inside the canvas
  await isolate.uncheck()                                                       // context view keeps the user's choice
  await expect(page.locator('.react-flow__node')).toHaveCount(overview)
  await page.getByRole('list', { name: 'Attack paths' }).locator('button').nth(2).click()
  await expect(isolate).not.toBeChecked()
})

test('phone 375px: with a path selected the graph labels are rendered at a legible size (not just CSS size)', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await load(page)
  await tab(page, 1)
  await page.getByRole('list', { name: 'Attack paths' }).locator('button').nth(1).click()
  await page.waitForTimeout(700)
  // rendered size = CSS font size x the viewport zoom, measured from the actual on-screen text box
  const rendered = await page.locator('.react-flow__node', { hasText: 'Jump Host' }).locator('.font-semibold').evaluate((el) => {
    const zoom = el.getBoundingClientRect().height / (el as HTMLElement).offsetHeight
    return parseFloat(getComputedStyle(el).fontSize) * zoom
  })
  expect(rendered).toBeGreaterThanOrEqual(11)
  expect(await overflow(page)).toBeLessThanOrEqual(0)
})

test('phone 375px: header controls and tabs stay reachable and the explanation panel fits', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await load(page)
  for (const name of NAV) await expect(page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name })).toBeVisible()
  await expect(page.getByTestId('lang-toggle')).toBeVisible()
  await tab(page, 1)
  await page.getByRole('list', { name: 'Attack paths' }).locator('button').first().click()
  await page.getByRole('button', { name: 'Explain this path' }).click()
  await expect(page.getByTestId('explanation')).toBeVisible()
  expect(await overflow(page)).toBeLessThanOrEqual(0)
  // simulation flow on a phone
  await tab(page, 2)
  await page.getByLabel('Target').selectOption('r03')
  await page.getByRole('button', { name: 'Add to queue' }).click()
  await page.getByRole('button', { name: 'Run simulation' }).click()
  await expect(page.getByTestId('comparison')).toBeVisible()
  expect(await overflow(page)).toBeLessThanOrEqual(0)
  // wide tables scroll inside their own container instead of widening the page
  await tab(page, 5)
  await page.getByRole('tab', { name: /Relationships/ }).click()
  expect(await overflow(page)).toBeLessThanOrEqual(0)
  const scrolls = await page.getByTestId('rel-table').evaluate((el) => el.scrollWidth > el.clientWidth)
  expect(scrolls).toBe(true)
})

test('RTL: header, navigation, cards, tables and the graph are mirrored; LTR is the exact opposite', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await load(page)
  const measure = async () => {
    const logo = await x(page.locator('header svg').first())
    const toggle = await x(page.getByTestId('lang-toggle'))
    const navButtons = page.getByRole('navigation', { name: 'Main' }).locator('button')
    const first = await x(navButtons.first())
    const last = await x(navButtons.last())
    const k = page.getByTestId('kpis').locator('> section')
    return { logo, toggle, first, last, kpi1: await x(k.nth(0)), kpi2: await x(k.nth(1)) }
  }
  const ltr = await measure()
  expect(ltr.logo).toBeLessThan(ltr.toggle)
  expect(ltr.first).toBeLessThan(ltr.last)
  expect(ltr.kpi1).toBeLessThan(ltr.kpi2)

  await page.getByTestId('lang-toggle').click()
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  const rtl = await measure()
  expect(rtl.logo).toBeGreaterThan(rtl.toggle)
  expect(rtl.first).toBeGreaterThan(rtl.last)
  expect(rtl.kpi1).toBeGreaterThan(rtl.kpi2)
  expect(await page.evaluate(() => getComputedStyle(document.body).direction)).toBe('rtl')

  // tables: first column on the right
  await tab(page, 5)
  const heads = page.getByTestId('asset-table').locator('th')
  expect(await x(heads.first())).toBeGreaterThan(await x(heads.last()))
  // graph: the layout is mirrored (the compromised account sits on the right, targets on the left)
  await tab(page, 1)
  const sara = await x(page.locator('.react-flow__node', { hasText: 'سارة' }))
  const db = await x(page.locator('.react-flow__node', { hasText: 'قاعدة بيانات العملاء' }))
  expect(sara).toBeGreaterThan(db)
  await page.getByTestId('lang-toggle').click()
  await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')
  const saraL = await x(page.locator('.react-flow__node', { hasText: 'Sara' }))
  const dbL = await x(page.locator('.react-flow__node', { hasText: 'Customer Database' }))
  expect(saraL).toBeLessThan(dbL)
})

test('Arabic activity feed never shows raw keys or English, whatever kinds of events occurred', async ({ page, api }) => {
  // generate every kind of event the backend can log
  const asset = { id: 'tmp-a', name: 'T', name_ar: 'ت', type: 'server', criticality: 1, exposure: 'internal', compromised: false, description: '', description_ar: '', controls: [] }
  await api.post('/api/assets', { data: asset })
  await api.put('/api/assets/tmp-a', { data: { ...asset, criticality: 2 } })
  await api.post('/api/relationships', { data: { id: 'tmp-r', source: 'emp-sara', target: 'tmp-a', type: 'trusts' } })
  await api.put('/api/relationships/tmp-r', { data: { id: 'tmp-r', source: 'emp-sara', target: 'tmp-a', type: 'trusts', disabled: true } })
  await api.delete('/api/relationships/tmp-r')
  await api.delete('/api/assets/tmp-a')
  await api.put('/api/environment', { data: await (await api.get('/api/environment')).json() })
  await api.post('/api/environment/undo')
  await api.post('/api/simulate', { data: { actions: [{ kind: 'remove_relationship', relationship_id: 'r03' }] } })
  const pid = (await (await api.get('/api/analysis')).json()).paths[0].id
  await api.post('/api/explain', { data: { kind: 'path', id: pid } })
  await api.post('/api/environment/reset')
  const kinds = new Set((await (await api.get('/api/activity?limit=200')).json()).map((e: { kind: string }) => e.kind))
  for (const k of ['asset_created', 'asset_updated', 'asset_deleted', 'relationship_created', 'relationship_updated', 'relationship_deleted',
    'environment_imported', 'environment_undo', 'environment_reset', 'simulation_run', 'explanation_requested']) expect(kinds.has(k), k).toBe(true)

  await page.setViewportSize({ width: 1440, height: 1200 })
  await load(page)
  await page.getByTestId('lang-toggle').click()
  const text = await page.getByTestId('activity').innerText()
  expect(text).not.toMatch(/act\./)
  expect(text).not.toMatch(/[A-Za-z]{4,}/)
  // and the English view shows readable labels, not keys
  await page.getByTestId('lang-toggle').click()
  const en = await page.getByTestId('activity').innerText()
  expect(en).not.toMatch(/act\.|_/)
})

test('RTL: Arabic inputs are right-to-left, forms lay out correctly, nothing is left untranslated', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await load(page)
  await page.getByTestId('lang-toggle').click()
  // "English" is the language-switch button, intentionally written in its own language; the rest are product/format names
  const ALLOW = new Set(['English', 'ATHAR', 'React', 'Flow', 'JSON', 'MFA', 'API', 'Enter', 'Escape', 'Tab', 'uvicorn', 'synthetic', 'true'])
  const latinWords = () => page.evaluate(() => {
    const out: string[] = []
    const w = document.createTreeWalker(document.querySelector('#root')!, NodeFilter.SHOW_TEXT)
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const el = n.parentElement!
      if (el.closest('.font-mono, script, style, option, [data-testid=attack-graph] .react-flow__controls, .react-flow__attribution')) continue
      for (const m of (n.textContent ?? '').matchAll(/[A-Za-z]{4,}/g)) out.push(m[0])
    }
    return out
  })
  const noLeaks = async (where: string) => expect((await latinWords()).filter((w) => !ALLOW.has(w)), `untranslated Latin words: ${where}`).toEqual([])

  for (const i of NAV.keys()) {
    await tab(page, i)
    await noLeaks(`tab ${NAV[i]}`)
  }
  // environment editor: tabs, both modal forms and their validation messages
  await tab(page, 5)
  await page.getByRole('button', { name: 'إضافة أصل' }).click()
  expect(await page.getByLabel('الاسم (عربي)').evaluate((el) => (el as HTMLInputElement).dir)).toBe('rtl')
  await page.getByRole('button', { name: 'حفظ' }).click()
  await expect(page.getByRole('dialog').getByText('هذا الحقل مطلوب.').first()).toBeVisible()   // translated client validation
  await noLeaks('asset dialog')
  await page.keyboard.press('Escape')
  await page.getByRole('tab', { name: /العلاقات/ }).click()
  await noLeaks('relationships tab')
  await page.getByRole('button', { name: 'إضافة علاقة' }).click()
  await noLeaks('relationship dialog')
})

test('route trace: the hero path reads in the language direction, and evidence is drawn as stroke patterns on the graph', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await load(page)
  const hero = page.getByTestId('hero-path')
  const ends = async () => {
    const items = hero.locator('ol > li')
    return { first: await x(items.first()), last: await x(items.last()), n: await items.count() }
  }
  const ltr = await ends()
  expect(ltr.n).toBeGreaterThanOrEqual(3)
  expect(ltr.first).toBeLessThan(ltr.last)                 // compromised start on the left, target on the right
  await page.getByTestId('lang-toggle').click()
  const rtl = await ends()
  expect(rtl.first).toBeGreaterThan(rtl.last)              // mirrored, not merely reversed text
  await page.getByTestId('lang-toggle').click()

  // graph edges: validated = solid, inferred = dashed, theoretical = dotted (never colour alone)
  await tab(page, 1)
  const dash = (id: string) => page.locator(`[data-testid="rf__edge-${id}"] path.react-flow__edge-path`).first().evaluate((p) => getComputedStyle(p).strokeDasharray)
  expect(await dash('r01')).toBe('none')                   // validated
  expect(await dash('r05')).toMatch(/8/)                   // inferred
  expect(await dash('r14')).toMatch(/2/)                   // theoretical (2 6)
  expect(await dash('r14')).not.toBe(await dash('r05'))
})

test('Arabic typography: Plex Arabic is loaded, no letter-spacing on Arabic text, tall line height', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await load(page)
  await page.getByTestId('lang-toggle').click()
  await page.evaluate(() => document.fonts.ready)
  const info = await page.evaluate(() => {
    const h = document.querySelector('main h1')!
    const s = getComputedStyle(h)
    const p = getComputedStyle(document.querySelector('main p')!)
    return { family: s.fontFamily, spacing: s.letterSpacing, lh: parseFloat(p.lineHeight) / parseFloat(p.fontSize), loaded: [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family) }
  })
  expect(info.family).toMatch(/IBM Plex Sans Arabic/)
  expect(['normal', '0px']).toContain(info.spacing)
  expect(info.lh).toBeGreaterThanOrEqual(1.5)
  expect(info.loaded.join(' ')).toMatch(/IBM Plex Sans Arabic/)
  // headings and labels anywhere in the Arabic UI must not be letter-spaced (it breaks Arabic joining)
  const spaced = await page.evaluate(() => [...document.querySelectorAll('main *')].filter((el) => {
    const ls = getComputedStyle(el).letterSpacing
    return ls !== 'normal' && ls !== '0px' && /[؀-ۿ]/.test(el.textContent ?? '')
  }).length)
  expect(spaced).toBe(0)
})
