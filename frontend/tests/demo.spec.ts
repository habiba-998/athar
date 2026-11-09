import { expect, test as base } from '@playwright/test'

const WEB = 'http://127.0.0.1:5184'
const API = 'http://127.0.0.1:8101'
const ADMIN = 'e2e-admin-token-0123456789-abcdef'
const test = base.extend({})
test.use({ baseURL: WEB })

async function openTab(page: import('@playwright/test').Page, name: string) {
  await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name }).click()
}

test('public demo: read-only banner, disabled editing, working analysis and stateless simulation', async ({ page, request }) => {
  await page.goto('/')
  await expect(page.getByTestId('kpis')).toBeVisible()
  await expect(page.getByTestId('chip-demo')).toContainText('read-only')
  await openTab(page, 'Environment')
  await expect(page.getByTestId('env-readonly')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Import JSON' }).first()).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Add asset' })).toHaveCount(0)
  await page.getByRole('tab', { name: /^Scenarios/ }).click()           // empty for the default sample, but the tab renders
  await openTab(page, 'Evidence')
  await page.getByTestId('subtab-assumptions').click()
  await expect(page.getByTestId('config-readonly')).toBeVisible()
  await expect(page.getByTestId('config-apply')).toBeDisabled()
  // a simulation runs and says it is not saved
  await openTab(page, 'Simulation')
  await page.getByLabel('Target').selectOption('r03')
  await page.getByRole('button', { name: 'Add to queue' }).click()
  await page.getByRole('button', { name: 'Run simulation' }).click()
  await expect(page.getByTestId('comparison')).toBeVisible()
  await expect(page.getByText('not saved in the public demo')).toBeVisible()
  // the server enforces it, not just the UI
  const write = await request.put(`${API}/api/environment/reset`, { data: {} })
  expect([403, 404, 405]).toContain(write.status())
  const reset = await request.post(`${API}/api/environment/reset`, { data: {} })
  expect(reset.status()).toBe(403)
  expect((await reset.json()).error).toBe('read_only_demo')
})

test('administrator sign-in enables editing for this browser tab only', async ({ page, request }) => {
  await page.goto('/')
  await expect(page.getByTestId('kpis')).toBeVisible()
  await page.getByTestId('admin-open').click()
  await page.getByLabel('API token').fill('wrong-token-wrong-token')
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByTestId('chip-demo')).toContainText('read-only')
  await page.getByTestId('admin-open').click()
  await page.getByLabel('API token').fill(ADMIN)
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByTestId('chip-demo')).toContainText('Administrator')
  await openTab(page, 'Environment')
  await expect(page.getByRole('button', { name: 'Add asset' })).toBeVisible()
  expect((await request.post(`${API}/api/environment/reset`, { data: {} })).status()).toBe(403)   // other clients stay read-only
})
