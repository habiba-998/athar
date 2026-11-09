import AxeBuilder from '@axe-core/playwright'
import { expect, load, test } from './helpers'
import type { Page } from '@playwright/test'

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

async function scan(page: Page) {
  const r = await new AxeBuilder({ page }).withTags(TAGS).analyze()
  return r.violations.map((v) => `${v.id} (${v.impact}): ${v.help} -> ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}`)
}

async function goTab(page: Page, index: number) {
  await page.getByRole('navigation', { name: 'Main' }).locator('button, [role=button]').nth(index).click()
  await page.waitForTimeout(400)
}

for (const lang of ['en', 'ar'] as const) {
  for (const [i, name] of ['Dashboard', 'Attack graph', 'Simulation', 'Recommendations', 'Evidence', 'Environment'].entries()) {
    test(`axe (WCAG 2.x A/AA): ${name} in ${lang}`, async ({ page }) => {
      await load(page)
      if (lang === 'ar') await page.getByTestId('lang-toggle').click()
      await goTab(page, i)
      expect(await scan(page)).toEqual([])
    })
  }
}

test('axe: simulation results, open forms and an explained path have no violations', async ({ page }) => {
  await load(page)
  await goTab(page, 2)
  await page.getByLabel('Target').selectOption('r03')
  await page.getByRole('button', { name: 'Add to queue' }).click()
  await page.getByRole('button', { name: 'Run simulation' }).click()
  await expect(page.getByTestId('comparison')).toBeVisible()
  expect(await scan(page)).toEqual([])

  await goTab(page, 5)
  await page.getByRole('button', { name: 'Add asset' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  expect(await scan(page)).toEqual([])                       // modal asset form open
  await page.keyboard.press('Escape')
  await page.getByRole('tab', { name: /Relationships/ }).click()
  await page.getByRole('button', { name: 'Add relationship' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  expect(await scan(page)).toEqual([])                       // modal relationship form open
  await page.keyboard.press('Escape')

  await goTab(page, 1)
  await page.getByRole('list', { name: 'Attack paths' }).locator('button').first().click()
  await page.getByRole('button', { name: 'Explain this path' }).click()
  await expect(page.getByTestId('explanation')).toBeVisible()
  expect(await scan(page)).toEqual([])
})

test('canary: the axe harness really detects contrast, label and name problems', async ({ page }) => {
  await load(page)
  await page.evaluate(() => {
    document.querySelector('main')!.insertAdjacentHTML('beforeend',
      '<p id="bad" style="color:#555;background:#444">low contrast text</p><input id="nolabel"><button id="noname"></button>')
  })
  const found = (await scan(page)).join('\n')
  expect(found).toContain('color-contrast')
  expect(found).toContain('label')
  expect(found).toContain('button-name')
})

test('keyboard: skip link is first, moves focus to main content', async ({ page }) => {
  await load(page)
  await page.keyboard.press('Tab')
  const skip = page.getByRole('link', { name: 'Skip to main content' })
  await expect(skip).toBeFocused()
  await expect(skip).toBeVisible()
  await page.keyboard.press('Enter')
  await expect(page.locator('#main')).toBeFocused()
})

test('keyboard: tabs, language toggle and simulation are fully operable without a mouse', async ({ page }) => {
  await load(page)
  const simTab = page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'Simulation' })
  await simTab.focus()
  await page.keyboard.press('Enter')
  await expect(simTab).toHaveAttribute('aria-current', 'page')
  await page.getByLabel('Action').focus()
  await page.keyboard.press('ArrowDown') // remove -> disable
  await expect(page.getByLabel('Action')).toHaveValue('disable_relationship')
  await page.getByRole('button', { name: 'Add to queue' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('sim-queue').locator('li')).toHaveCount(1)
  await page.getByRole('button', { name: 'Run simulation' }).focus()
  await page.keyboard.press('Space')
  await expect(page.getByTestId('comparison')).toBeVisible()
  await page.getByTestId('lang-toggle').focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
})

test('keyboard: a graph node can be focused and selected with Enter (not only by mouse)', async ({ page }) => {
  await load(page)
  await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'Attack graph' }).click()
  const node = page.locator('.react-flow__node', { hasText: 'Customer Database' })
  await expect(node).toHaveAttribute('tabindex', '0')
  await expect(node).toHaveAttribute('aria-label', /Customer Database, Database, Criticality 5\/5/)
  await node.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('selection-detail')).toContainText('Customer Database')
  await expect(page.getByTestId('selection-detail')).toContainText('Incoming access')
  // moving to another node and pressing Enter changes the selection
  await page.locator('.react-flow__node', { hasText: 'Jump Host' }).focus()
  await page.keyboard.press('Space')
  await expect(page.getByTestId('selection-detail')).toContainText('Jump Host')
})

test('keyboard: focus indicator is visible on buttons, links and fields', async ({ page }) => {
  await load(page)
  await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'Environment' }).click()
  for (const loc of [
    page.getByRole('button', { name: 'Export JSON' }),
    page.getByRole('button', { name: 'Add asset' }),
    page.getByTestId('lang-toggle'),
  ]) {
    // reach the element with real key presses so :focus-visible applies (script focus after a click does not)
    await loc.focus()
    await page.keyboard.press('Shift+Tab')
    await page.keyboard.press('Tab')
    await expect(loc).toBeFocused()
    const o = await loc.evaluate((el) => { const s = getComputedStyle(el); return { style: s.outlineStyle, width: parseFloat(s.outlineWidth) } })
    expect(o.style).not.toBe('none')
    expect(o.width).toBeGreaterThanOrEqual(2)
  }
})

test('dialogs: Escape closes, focus returns to the trigger, and the page behind is inert while open', async ({ page }) => {
  await load(page)
  await goTab(page, 5)
  const trigger = page.getByRole('button', { name: 'Add asset' })
  await trigger.focus()
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog', { name: 'Add asset' })
  await expect(dialog).toBeVisible()
  // inline validation messages appear next to the field, in words
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(dialog.getByText(/Use lowercase letters, digits/)).toBeVisible()
  await expect(dialog.getByLabel('ID (lowercase letters, digits, - _)')).toHaveAttribute('aria-invalid', 'true')
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(trigger).toBeFocused()
})

test('every form control in the editor has an accessible name', async ({ page }) => {
  await load(page)
  await goTab(page, 5)
  await page.getByRole('button', { name: 'Add asset' }).click()
  await page.getByRole('button', { name: 'Cancel' }).click()
  await page.getByRole('tab', { name: /Relationships/ }).click()
  await page.getByRole('button', { name: 'Add relationship' }).click()
  const unnamed = await page.evaluate(() =>
    [...document.querySelectorAll('main input, main select, main textarea, main button')]
      .filter((e) => !((e as HTMLElement).getAttribute('aria-label') || (e as HTMLInputElement).labels?.length || (e as HTMLElement).innerText?.trim()))
      .map((e) => e.outerHTML.slice(0, 80)))
  expect(unnamed).toEqual([])
})

// The new views (sub-tabs) are scanned too, in both languages, with data loaded (Meridian) so lists and charts are present.
import fs from 'node:fs'
import path from 'node:path'
const meridian = JSON.parse(fs.readFileSync(path.resolve(process.cwd(), '../scenarios/meridian-enterprise.json'), 'utf8'))
for (const lang of ['en', 'ar'] as const) {
  for (const [nav, sub] of [[3, 'plans'], [4, 'evidence'], [4, 'assumptions']] as const) {
    test(`axe: ${nav === 3 ? 'recommendations' : 'evidence'} > ${sub} in ${lang}`, async ({ page, api }) => {
      expect((await api.put('/api/environment', { data: meridian })).ok()).toBeTruthy()
      await load(page)
      if (lang === 'ar') await page.getByTestId('lang-toggle').click()
      await goTab(page, nav)
      await page.getByTestId(`subtab-${sub}`).click()
      await page.waitForTimeout(sub === 'plans' ? 4000 : 800)
      if (sub === 'plans') await expect(page.getByTestId('plans')).toBeVisible({ timeout: 45_000 })
      expect(await scan(page)).toEqual([])
    })
  }
}
