import fs from 'node:fs'
import path from 'node:path'
import { expect, load, openTab, test } from './helpers'
import type { APIRequestContext, Page } from '@playwright/test'

const meridian = JSON.parse(fs.readFileSync(path.resolve(process.cwd(), '../scenarios/meridian-enterprise.json'), 'utf8'))

async function useMeridian(api: APIRequestContext) {
  expect((await api.put('/api/environment', { data: meridian })).ok()).toBeTruthy()
}
async function plansTab(page: Page) {
  await openTab(page, 'Recommendations')
  await page.getByTestId('subtab-plans').click()
  await expect(page.getByTestId('plans')).toBeVisible({ timeout: 45_000 })
}

test.describe('plans and Pareto comparison', () => {
  test('compare plans: suggestion, honest framing, reversible plan simulated end to end', async ({ page, api }) => {
    await useMeridian(api)
    await load(page)
    await plansTab(page)
    await expect(page.getByTestId('plans')).toContainText('not a claim that a plan is the best possible')
    await expect(page.getByTestId('plan-suggested')).toContainText('Smallest change')
    // the plan that removes every path is shown, rated high impact, and is NOT the suggestion
    const maxCard = page.getByTestId('plan-card-max_reduction')
    await expect(maxCard).toContainText('0')
    await expect(maxCard).toContainText('High')
    await page.getByTestId('plan-card-reversible').click()
    await expect(page.locator('#plan-detail')).toContainText('Reversible only')
    await expect(page.getByTestId('plan-services')).toBeVisible()
    await page.getByTestId('plan-simulate').click()
    await expect(page.getByTestId('sim-queue').locator('li')).toHaveCount(2)
    await page.getByRole('button', { name: 'Run simulation' }).click()
    await expect(page.getByTestId('eliminated-count')).toBeVisible()
    const live = await (await api.get('/api/analysis')).json()
    expect(live.summary.attack_paths).toBe(71)                                       // the live environment is untouched
  })

  test('decision record downloads in the interface language', async ({ page, api }) => {
    await useMeridian(api)
    await load(page)
    await plansTab(page)
    await page.getByTestId('plan-card-balanced').click()
    const [dl] = await Promise.all([page.waitForEvent('download'), page.getByTestId('plan-report').click()])
    expect(dl.suggestedFilename()).toMatch(/decision-record-plan-balanced-en\.md$/)
    const text = fs.readFileSync((await dl.path())!, 'utf8')
    expect(text).toContain('# ATHAR decision record')
    expect(text).toContain('global optimality')
  })

  test('Arabic: plans render right-to-left with Arabic names and an Arabic record', async ({ page, api }) => {
    await useMeridian(api)
    await load(page)
    await page.getByTestId('lang-toggle').click()
    await openTab(page, 'التوصيات')
    await page.getByTestId('subtab-plans').click()
    await expect(page.getByTestId('plans')).toContainText('باريتو', { timeout: 45_000 })
    expect(await page.evaluate(() => document.documentElement.dir)).toBe('rtl')
    await page.getByTestId('plan-card-reversible').click()
    await expect(page.locator('#plan-detail')).toContainText('قابلة للتراجع فقط')
  })
})

test.describe('evidence explorer', () => {
  test('shows the four classes, zero real-world validation, and provenance per relationship', async ({ page, api }) => {
    await useMeridian(api)
    await load(page)
    await openTab(page, 'Evidence')
    await expect(page.getByTestId('evidence')).toContainText('never verifies or upgrades it')
    await expect(page.getByTestId('val-real_world')).toHaveText('0')
    await expect(page.getByTestId('evidence-summary')).toContainText('Observed')
    await page.getByLabel('Evidence class').selectOption('theoretical')
    const rows = page.getByTestId('evidence-rows').locator('li')
    await expect(rows).toHaveCount(2)
    await expect(rows.first()).toContainText('synthetic:architecture-assumption')
  })
})

test.describe('assumptions and sensitivity', () => {
  test('changing a weight recomputes the results; invalid orderings are rejected before sending; reset restores', async ({ page, api }) => {
    await load(page)
    await openTab(page, 'Dashboard')
    const before = await page.getByTestId('posture').innerText()
    await openTab(page, 'Evidence')
    await page.getByTestId('subtab-assumptions').click()
    const cfg = page.getByTestId('scoring-config')
    const inferred = cfg.getByLabel('Evidence weight: inferred')
    await inferred.fill('0.99')                                                       // above observed: invalid
    await expect(page.getByRole('alert').filter({ hasText: 'theoretical ≤ inferred ≤ observed' })).toBeVisible()
    await expect(page.getByTestId('config-apply')).toBeDisabled()
    await inferred.fill('0.5')
    await cfg.getByLabel('Evidence weight: theoretical').fill('0.3')
    await page.getByTestId('config-apply').click()
    await expect(page.getByText('Weights applied')).toBeVisible()
    await openTab(page, 'Dashboard')
    expect(await page.getByTestId('posture').innerText()).not.toBe(before)
    await openTab(page, 'Evidence')
    await page.getByTestId('subtab-assumptions').click()
    await page.getByTestId('config-reset').click()
    await expect(page.getByText('Defaults restored')).toBeVisible()
    await openTab(page, 'Dashboard')
    expect(await page.getByTestId('posture').innerText()).toBe(before)
    expect((await (await api.get('/api/scoring-config')).json()).is_default).toBe(true)
  })

  test('sensitivity analysis: ranges, stability and the not-a-probability notice', async ({ page }) => {
    await load(page)
    await openTab(page, 'Evidence')
    await page.getByTestId('subtab-assumptions').click()
    await page.getByTestId('sens-run').click()
    await expect(page.getByTestId('sens-result')).toBeVisible({ timeout: 60_000 })
    await expect(page.getByTestId('sens-result')).toContainText('not confidence intervals and not probabilities')
    await expect(page.getByTestId('sens-recs').locator('li').first()).toBeVisible()
  })
})

test.describe('business context and scenarios', () => {
  test('services list their access requirements; activating a scenario changes the starting points and can be undone', async ({ page, api }) => {
    await useMeridian(api)
    await load(page)
    await openTab(page, 'Environment')
    await page.getByRole('tab', { name: /^Services/ }).click()
    await expect(page.getByTestId('services')).toContainText('Online ordering')
    await expect(page.getByTestId('services')).toContainText('Depends on')
    await page.getByRole('tab', { name: /^Scenarios/ }).click()
    await page.getByTestId('scenario-sc-vendor').click()
    await expect.poll(async () => (await (await api.get('/api/analysis')).json()).paths.every((p: { source: string }) => p.source === 'u-vendor')).toBe(true)
    await page.getByRole('button', { name: 'Undo last edit' }).click()
    await expect.poll(async () => (await (await api.get('/api/analysis')).json()).summary.attack_paths).toBe(71)
    await page.getByRole('tab', { name: /^Audit/ }).click()
    await expect(page.getByTestId('audit')).toContainText('Environment edit undone')
  })
})

test.describe('attack graph additions', () => {
  test('search highlights, evidence filter hides edges, full screen toggles and Escape leaves it', async ({ page, api }) => {
    await useMeridian(api)
    await load(page)
    await openTab(page, 'Attack graph')
    await expect(page.locator('.react-flow__node').first()).toBeVisible()
    // sensitive assets get a visible marker
    await expect(page.locator('.react-flow__node [data-sensitive]').first()).toBeVisible()
    const edges = await page.locator('.react-flow__edge').count()
    await page.getByTestId('evidence-filter-toggle').click()
    await page.getByTestId('evidence-filter').getByLabel('Observed').uncheck()
    await expect.poll(() => page.locator('.react-flow__edge').count()).toBeLessThan(edges)
    await page.getByTestId('graph-search').fill('jump')
    await expect(page.locator('.react-flow__node.selectable', { hasText: 'Admin jump host' }).first()).toBeVisible()
    await page.getByTestId('graph-fullscreen').click()
    await expect(page.getByTestId('graph-region')).toHaveAttribute('data-expanded', 'true')
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('graph-region')).not.toHaveAttribute('data-expanded', 'true')
  })

  test('an isolated path shows the full evidence chain with sources, confidence and the weakest hop', async ({ page, api }) => {
    await useMeridian(api)
    await load(page)
    await openTab(page, 'Attack graph')
    await page.getByRole('list', { name: 'Attack paths' }).locator('button').first().click()
    const detail = page.getByTestId('path-detail')
    await expect(detail).toContainText('synthetic:')
    await expect(detail.getByTestId('weakest-hop')).toHaveCount(1)
    await expect(detail.getByTestId('path-drivers')).toBeVisible()
  })
})

test('nine questions: every recommendation can be explained in the interface language', async ({ page, api }) => {
  await useMeridian(api)
  await load(page)
  await openTab(page, 'Recommendations')
  await page.getByTestId('recommendations').locator('li').first().getByRole('button', { name: /Explain/ }).click()
  const nine = page.getByTestId('rec-nine').first()
  await expect(nine).toContainText('What evidence supports it?')
  await expect(nine).toContainText('not a probability')
  await expect(nine.locator('dt')).toHaveCount(9)
})
