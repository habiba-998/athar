import { devices, expect, test as base } from '@playwright/test'
import { API } from './helpers'

/**
 * Device emulation: Android (Pixel 7) and iPhone (iPhone 14) viewports, touch input and user agents, plus a desktop run.
 * HONEST LIMIT: all three run on Chromium. The iPhone profile reproduces Safari's viewport, pixel ratio, touch and user agent
 * but NOT the WebKit engine, so it cannot catch Safari-only rendering bugs. Real-device checks are listed in docs/DEPLOYMENT.md.
 */
const { defaultBrowserType: _a, ...pixel } = devices['Pixel 7']
const { defaultBrowserType: _b, ...iphone } = devices['iPhone 14']
const desktop = { viewport: { width: 1440, height: 900 } }

for (const [name, profile] of [['Android (Pixel 7)', pixel], ['iPhone 14', iphone], ['desktop 1440', desktop]] as const) {
  for (const lang of ['en', 'ar'] as const) {
    const test = base.extend({})
    test.describe(`${name} ${lang}`, () => {
      test.use(profile)
      test.beforeEach(async ({ playwright }) => {
        const ctx = await playwright.request.newContext({ baseURL: API })
        await ctx.post('/api/scoring-config/reset')
        await ctx.post('/api/environment/reset')
        await ctx.dispose()
      })

      test('loads, switches language, navigates every tab by touch/click without horizontal scroll', async ({ page, isMobile }) => {
        await page.goto('/')
        await expect(page.getByTestId('kpis')).toBeVisible()
        if (lang === 'ar') { if (isMobile) await page.getByTestId('lang-toggle').tap(); else await page.getByTestId('lang-toggle').click() }
        if (lang === 'ar') await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
        else await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')
        const buttons = page.getByRole('navigation', { name: 'Main' }).locator('button')
        for (let i = 0; i < (await buttons.count()); i++) {
          if (isMobile) await buttons.nth(i).tap(); else await buttons.nth(i).click()
          await page.waitForTimeout(250)
          const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
          expect(overflow, `tab ${i}`).toBeLessThanOrEqual(0)
        }
      })

      test('graph: choose a path, see it isolated; simulate the top recommendation and read the result', async ({ page, isMobile }) => {
        await page.goto('/')
        await expect(page.getByTestId('kpis')).toBeVisible()
        if (lang === 'ar') await page.getByTestId('lang-toggle').click()
        const nav = page.getByRole('navigation', { name: 'Main' }).locator('button')
        const press = async (loc: import('@playwright/test').Locator) => (isMobile ? loc.tap() : loc.click())
        await press(nav.nth(1))
        const first = page.locator('ul[aria-label] button[aria-pressed]').first()
        await press(first)
        await expect(page.locator('.react-flow__node').first()).toBeVisible()
        await expect(page.getByTestId('path-detail')).toBeVisible()
        await press(nav.nth(3))                                                   // recommendations
        await press(page.getByTestId('recommendations').locator('li').first().locator('button').first())
        await expect(page.getByTestId('sim-queue')).toBeVisible()                  // landed on the simulation tab with the action queued
        await press(page.getByTestId('sim-run'))
        await expect(page.getByTestId('comparison')).toBeVisible()
        const live = await (await page.request.get(`${API}/api/analysis`)).json()
        expect(live.summary.attack_paths).toBeGreaterThan(0)                       // live environment untouched
      })
    })
  }
}
