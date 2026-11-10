import { expect, test } from '@playwright/test'

/**
 * The STATIC build: no server at all. The unchanged Python backend runs in the browser (Pyodide in a Web Worker). These tests run the
 * real production bundle behind the real production security headers (CSP with only 'wasm-unsafe-eval') and prove that:
 * every feature still works, nothing is requested from any other origin, and no API request ever leaves the page.
 */
const WEB = process.env.ATHAR_STATIC_URL ?? 'http://127.0.0.1:5185'   // set ATHAR_STATIC_URL to run the same checks against a deployed site
test.use({ baseURL: WEB })
test.describe.configure({ mode: 'serial' })
test.setTimeout(180_000)

async function open(page: import('@playwright/test').Page) {
  const requests: string[] = []
  const errors: string[] = []
  page.on('request', (r) => requests.push(r.url()))
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text().slice(0, 300)) })
  page.on('pageerror', (e) => errors.push(String(e).slice(0, 300)))
  await page.goto('/')
  await expect(page.getByTestId('kpis')).toBeVisible({ timeout: 150_000 })
  return { requests, errors }
}

const nav = (page: import('@playwright/test').Page, name: string) => page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name }).click()

test('the engine starts in the browser, the dashboard shows real analysis, and nothing leaves the origin', async ({ page }) => {
  const { requests, errors } = await open(page)
  await expect(page.getByTestId('chip-engine')).toContainText('in your browser')
  await expect(page.getByTestId('chip-demo')).toContainText('read-only')
  await expect(page.getByTestId('kpis')).toContainText('20')                                   // the sample environment's 20 attack paths
  await expect(page.getByTestId('posture')).toContainText('54.8')
  const origins = new Set(requests.map((u) => new URL(u).origin).filter((o) => o !== 'null'))
  expect([...origins].filter((o) => o !== WEB)).toEqual([])                                    // no third-party request, no CDN
  expect(requests.filter((u) => new URL(u).pathname.startsWith('/api/'))).toEqual([])         // no API call ever reaches a server
  expect(requests.some((u) => u.endsWith('.wasm'))).toBeTruthy()
  expect(errors).toEqual([])                                                                    // and the strict CSP blocked nothing
})

test('the production page carries the strict security headers, including the WebAssembly allowance and nothing broader', async ({ request }) => {
  const r = await request.get('/')
  const csp = r.headers()['content-security-policy']
  expect(csp).toContain("script-src 'self' 'wasm-unsafe-eval'")
  expect(csp.replace("'wasm-unsafe-eval'", '')).not.toContain('unsafe-eval')
  expect(csp).toContain("frame-ancestors 'none'")
  expect(r.headers()['x-content-type-options']).toBe('nosniff')
  expect(r.headers()['x-frame-options']).toBe('DENY')
})

test('plans, simulation, sensitivity and the explanation questions all run in the browser', async ({ page }) => {
  await open(page)
  await nav(page, 'Recommendations')
  await page.getByTestId('recommendations').locator('li').first().getByRole('button', { name: /Explain/ }).click()
  await expect(page.getByTestId('rec-nine').first()).toContainText('What evidence supports it?')
  await page.getByTestId('subtab-plans').click()
  await expect(page.getByTestId('plans')).toBeVisible({ timeout: 90_000 })
  await expect(page.getByTestId('plan-suggested')).toBeVisible()
  await page.getByTestId('plan-card-reversible').click()
  await page.getByTestId('plan-simulate').click()
  await page.getByTestId('sim-run').click()
  await expect(page.getByTestId('comparison')).toBeVisible({ timeout: 60_000 })
  await expect(page.getByText('not saved in the public demo')).toBeVisible()
  await nav(page, 'Evidence')
  await page.getByTestId('subtab-assumptions').click()
  await page.getByTestId('sens-run').click()
  await expect(page.getByTestId('sens-result')).toBeVisible({ timeout: 120_000 })
})

test('it is read-only: editing and weight changes are disabled, the server-side guard answers inside the browser', async ({ page }) => {
  await open(page)
  await nav(page, 'Environment')
  await expect(page.getByTestId('env-readonly')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Import JSON' }).first()).toBeDisabled()
  await nav(page, 'Evidence')
  await page.getByTestId('subtab-assumptions').click()
  await expect(page.getByTestId('config-apply')).toBeDisabled()
})

test('Arabic RTL works and a phone-width window does not overflow', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await open(page)
  await page.getByTestId('lang-toggle').click()
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expect(page.getByTestId('chip-demo')).toContainText('للقراءة فقط')
  for (const i of [0, 1, 2, 3, 4, 5]) {
    await page.getByRole('navigation', { name: 'Main' }).locator('button').nth(i).click()
    await page.waitForTimeout(400)
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), `tab ${i}`).toBeLessThanOrEqual(0)
  }
})
