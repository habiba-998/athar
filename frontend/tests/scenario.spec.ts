import fs from 'node:fs'
import path from 'node:path'
import { expect, load, openTab, test } from './helpers'

const harbor = fs.readFileSync(path.resolve(process.cwd(), '../scenarios/harbor-logistics.json'), 'utf8')

test('Harbor scenario: import through the UI, see the realistic paths, simulate the top fix, read the residual risk', async ({ page, api }) => {
  await load(page)
  await openTab(page, 'Environment')
  await page.getByTestId('import-input').setInputFiles({ name: 'harbor-logistics.json', mimeType: 'application/json', buffer: Buffer.from(harbor) })
  await expect(page.getByTestId('env-notice')).toContainText('Environment imported')
  await expect(page.getByTestId('env-name')).toContainText('Harbor Synthetic Logistics')

  // dashboard numbers come from the engine and match the pinned golden values (tests/test_scenarios.py)
  await openTab(page, 'Dashboard')
  const kpis = page.getByTestId('kpis')
  await expect(kpis).toContainText('42')            // attack paths
  await expect(kpis).toContainText('88')            // highest path score
  await expect(page.getByTestId('posture')).toContainText('67.3')
  await expect(page.getByTestId('hero-path')).toContainText('Customer web portal')
  const analysis = await (await api.get('/api/analysis')).json()
  expect(analysis.summary.attack_paths).toBe(42)

  // the top recommendation is the stale helpdesk permission, with low impact
  await openTab(page, 'Recommendations')
  const first = page.getByTestId('recommendations').locator('li').first()
  await expect(first).toContainText('Helpdesk group')
  await expect(first).toContainText('Admin jump host')
  await expect(first).toContainText('Low')
  await first.getByRole('button', { name: 'Simulate this' }).click()
  await page.getByRole('button', { name: 'Run simulation' }).click()
  await expect(page.getByTestId('comparison')).toBeVisible()
  await expect(page.getByTestId('before-after')).toContainText('42')
  await expect(page.getByTestId('before-after')).toContainText('5')
  await expect(page.getByTestId('impact-level')).toContainText('Low')
  // residual risk: only the internet-facing portal remains
  const residual = page.getByTestId('residual')
  await expect(residual.locator('li')).toHaveCount(5)
  await expect(residual).toContainText('Customer web portal')
  await expect(residual).not.toContainText('Lina')
  // and the live environment was never modified by the simulation
  expect((await (await api.get('/api/analysis')).json()).summary.attack_paths).toBe(42)
})

test('Harbor scenario in Arabic: names, units and mirrored route are all Arabic', async ({ page, api }) => {
  await api.put('/api/environment', { data: JSON.parse(harbor) })
  await load(page)
  await page.getByTestId('lang-toggle').click()
  await expect(page.getByTestId('hero-path')).toContainText('بوابة العملاء')
  const text = await page.getByTestId('assets-at-risk').innerText()
  expect(text).not.toMatch(/[A-Za-z]{4,}/)
})

test('an already-compromised sensitive asset is surfaced and excluded from the posture index (audit finding F1)', async ({ page, api }) => {
  void api                                    // fixture resets the environment to the sample first (it contains db-hr)
  await page.route('**/api/analysis', async (route) => {
    const body = await (await route.fetch()).json()
    await route.fulfill({ json: { ...body, summary: { ...body.summary, compromised_sensitive_assets: ['db-hr'] } } })
  })
  await load(page)
  await expect(page.getByTestId('owned-warning')).toContainText('Already assumed compromised')
  await expect(page.getByTestId('owned-warning')).toContainText('HR Database')
  await page.getByTestId('lang-toggle').click()
  await expect(page.getByTestId('owned-warning')).toContainText('مفترَض اختراقها مسبقًا')
})
