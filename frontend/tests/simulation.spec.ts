import { expect, load, openTab, test } from './helpers'

async function queue(page: import('@playwright/test').Page, action: string, target: string) {
  await page.getByLabel('Action').selectOption(action)
  await page.getByLabel('Target').selectOption(target)
  await page.getByRole('button', { name: 'Add to queue' }).click()
}

test('Disable relationship is a distinct, reversible action with exact affected assets', async ({ page, api }) => {
  await load(page)
  await openTab(page, 'Simulation')
  await expect(page.getByLabel('Action').locator('option')).toContainText(['Remove permission', 'Disable relationship (reversible)'])
  await queue(page, 'disable_relationship', 'r03')
  await page.getByRole('button', { name: 'Run simulation' }).click()
  await expect(page.getByTestId('comparison')).toBeVisible()
  await expect(page.getByText('Every change in this simulation can be reverted.')).toBeVisible()
  const assets = page.getByTestId('affected-assets')
  await expect(assets.locator('li')).toHaveText(['Sara (Employee)', 'Jump Host'])
  await expect(page.getByTestId('lost-access')).toContainText('No legitimate identity loses access')
  expect((await (await api.get('/api/environment')).json()).relationships.find((r: { id: string }) => r.id === 'r03').disabled).toBe(false) // server graph untouched
})

test('Remove permission is reported as not reversible', async ({ page }) => {
  await load(page)
  await openTab(page, 'Simulation')
  await queue(page, 'remove_relationship', 'r03')
  await page.getByRole('button', { name: 'Run simulation' }).click()
  await expect(page.getByTestId('comparison')).toBeVisible()
  await expect(page.getByText('Not reversible').first()).toBeVisible()
})

test('lost legitimate access is listed by name', async ({ page }) => {
  await load(page)
  await openTab(page, 'Simulation')
  await queue(page, 'remove_relationship', 'r17') // HR's only route to the HR database
  await page.getByRole('button', { name: 'Run simulation' }).click()
  await expect(page.getByTestId('lost-access')).toContainText('Omar (HR) → HR Database')
  await expect(page.getByTestId('impact-level')).toContainText('High')
})

test('every action type runs from the UI', async ({ page }) => {
  await load(page)
  await openTab(page, 'Simulation')
  for (const [action, target] of [
    ['remove_relationship', 'r03'], ['disable_relationship', 'r05'], ['reduce_privilege', 'r06'],
    ['apply_mfa', 'web-portal'], ['apply_segmentation', 'app-server'],
  ]) await queue(page, action, target)
  await expect(page.getByTestId('sim-queue').locator('li')).toHaveCount(5)
  await page.getByRole('button', { name: 'Run simulation' }).click()
  await expect(page.getByTestId('comparison')).toBeVisible()
  // together these five changes leave no attack path at all (checked against the engine), and the UI says so
  await expect(page.getByText('No attack paths remain.')).toBeVisible()
  await expect(page.getByTestId('comparison')).toContainText('20')
  await expect(page.getByTestId('impact-level')).toContainText('High')
  await expect(page.getByTestId('affected-assets').locator('li')).not.toHaveCount(0)
})

test('undo removes the last queued change and re-runs; undoing everything clears the result', async ({ page }) => {
  await load(page)
  await openTab(page, 'Simulation')
  await queue(page, 'remove_relationship', 'r03')
  await queue(page, 'remove_relationship', 'r05')
  await page.getByRole('button', { name: 'Run simulation' }).click()
  await expect(page.getByTestId('comparison')).toBeVisible()
  const afterTwo = await page.getByTestId('comparison').innerText()
  await page.getByRole('button', { name: 'Undo last change' }).click()
  await expect(page.getByTestId('sim-queue').locator('li')).toHaveCount(1)
  await expect.poll(async () => page.getByTestId('comparison').innerText()).not.toBe(afterTwo)
  await page.getByRole('button', { name: 'Undo last change' }).click()
  await expect(page.getByText('No changes queued.')).toBeVisible()
  await expect(page.getByTestId('comparison')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Undo last change' })).toBeDisabled()
})

test('simulation errors from the server are shown, not swallowed', async ({ page }) => {
  await load(page)
  await openTab(page, 'Simulation')
  await queue(page, 'apply_mfa', 'app-server') // no login edges into app-server
  await page.getByRole('button', { name: 'Run simulation' }).click()
  await expect(page.getByRole('alert')).toContainText('no login/credential relationships')
})

test('runs are saved with timestamps; viewing an old run after an edit warns it is stale', async ({ page, api }) => {
  await load(page)
  await openTab(page, 'Simulation')
  await queue(page, 'remove_relationship', 'r03')
  await page.getByRole('button', { name: 'Run simulation' }).click()
  await expect(page.getByTestId('comparison')).toBeVisible()
  const history = page.getByTestId('sim-history')
  await expect(history.locator('li').first()).toContainText(/\d{4}-\d\d-\d\d \d\d:\d\d:\d\d/)
  await expect(history.locator('li').first()).toContainText('20 → 11')
  const recorded = await (await api.get('/api/simulations')).json()
  expect(recorded[0].actions).toEqual([{ kind: 'remove_relationship', relationship_id: 'r03' }])

  await api.delete('/api/relationships/r05') // environment changes behind the saved run
  await openTab(page, 'Dashboard')
  await openTab(page, 'Simulation')
  await page.getByRole('button', { name: /^View #/ }).first().click()
  await expect(page.getByRole('status')).toContainText('The environment has changed since this run')
  await expect(page.getByTestId('comparison')).toBeVisible()
})
