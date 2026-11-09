import { expect, load, openTab, test } from './helpers'

test('token mode: UI asks for the token, rejects a wrong one, accepts the right one, keeps it per-tab only', async ({ page }) => {
  await page.route('**/api/**', (route) => {
    const url = route.request().url()
    if (url.endsWith('/api/auth/status')) return route.fulfill({ json: { token_required: true } })
    if (route.request().headers()['x-athar-token'] === 'good-token') return route.continue()
    return route.fulfill({ status: 401, json: { error: 'invalid_or_missing_token' } })
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Access token required' })).toBeVisible()
  await expect(page.getByTestId('kpis')).toHaveCount(0)             // nothing loads without a token

  await page.getByLabel('API token').fill('wrong')
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByRole('alert')).toContainText('The token was not accepted')
  expect(await page.evaluate(() => sessionStorage.getItem('athar.token'))).toBeNull()   // bad token is discarded

  await page.getByLabel('API token').fill('good-token')
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByTestId('kpis')).toBeVisible()
  expect(await page.evaluate(() => localStorage.length)).toBe(0)                          // never persisted beyond the tab
  expect(await page.evaluate(() => sessionStorage.getItem('athar.token'))).toBe('good-token')
  await openTab(page, 'Environment')                                                      // authenticated writes work too
  await page.getByRole('button', { name: 'Load sample' }).click()
  await expect(page.getByTestId('env-notice')).toContainText('restored')
})

test('token mode: a token that stops being valid returns the user to the prompt', async ({ page }) => {
  let valid = true
  await page.route('**/api/**', (route) => {
    if (route.request().url().endsWith('/api/auth/status')) return route.fulfill({ json: { token_required: true } })
    if (valid && route.request().headers()['x-athar-token'] === 'good-token') return route.continue()
    return route.fulfill({ status: 401, json: { error: 'invalid_or_missing_token' } })
  })
  await page.addInitScript(() => sessionStorage.setItem('athar.token', 'good-token'))
  await page.goto('/')
  await expect(page.getByTestId('kpis')).toBeVisible()
  valid = false
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Access token required' })).toBeVisible()
})

test('AI narration returned by the server is shown in a separate, labelled block', async ({ page }) => {
  await page.route('**/api/ai/status', (r) => r.fulfill({ json: { enabled: true, provider: 'anthropic', reason: 'ok' } }))
  await page.route('**/api/explain', async (route) => {
    const real = await route.fetch()
    const body = await real.json()
    await route.fulfill({ json: { ...body, ai_explanation: 'AI SAYS: this is narration text.', ai_status: 'ok' } })
  })
  await load(page)
  await expect(page.getByTestId('chip-ai')).toContainText('on')
  await openTab(page, 'Attack graph')
  await page.getByRole('list', { name: 'Attack paths' }).locator('button').first().click()
  await page.getByRole('button', { name: 'Explain this path' }).click()
  const ai = page.getByTestId('ai-section')
  await expect(ai).toContainText('AI-generated narration (not evidence)')
  await expect(page.getByTestId('ai-text')).toHaveText('AI SAYS: this is narration text.')
  // the deterministic blocks do not contain the AI text
  const deterministicOnly = await page.getByTestId('explanation').evaluate((el) => {
    const clone = el.cloneNode(true) as HTMLElement
    clone.querySelector('[data-testid=ai-section]')?.remove()
    return clone.innerText
  })
  expect(deterministicOnly).not.toContain('AI SAYS')
  expect(deterministicOnly).toContain('Route:')
  await expect(page.getByTestId('explanation')).toContainText('Evidence (deterministic)')
})

test('AI failure falls back to deterministic text with an honest message', async ({ page }) => {
  await page.route('**/api/explain', async (route) => {
    const body = await (await route.fetch()).json()
    await route.fulfill({ json: { ...body, ai_explanation: null, ai_status: 'ai_unavailable' } })
  })
  await load(page)
  await openTab(page, 'Attack graph')
  await page.getByRole('list', { name: 'Attack paths' }).locator('button').first().click()
  await page.getByRole('button', { name: 'Explain this path' }).click()
  await expect(page.getByTestId('ai-fallback')).toContainText('AI narration was unavailable')
  await expect(page.getByTestId('explanation')).toContainText('Route:')
  await expect(page.getByTestId('ai-text')).toHaveCount(0)
})

test('a configured-but-keyless provider is reported as such', async ({ page }) => {
  await page.route('**/api/explain', async (route) => {
    const body = await (await route.fetch()).json()
    await route.fulfill({ json: { ...body, ai_explanation: null, ai_status: 'ai_not_configured' } })
  })
  await load(page)
  await openTab(page, 'Attack graph')
  await page.getByRole('list', { name: 'Attack paths' }).locator('button').first().click()
  await page.getByRole('button', { name: 'Explain this path' }).click()
  await expect(page.getByTestId('ai-fallback')).toContainText('no API key is configured')
})
