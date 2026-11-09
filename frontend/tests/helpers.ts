import { expect, test as base, type APIRequestContext, type Page } from '@playwright/test'

export const API = 'http://127.0.0.1:8100'

/** Every test starts from the sample environment (server state is shared and persisted). */
export const test = base.extend<{ api: APIRequestContext }>({
  // auto: every test starts from the sample environment and default weights, even if it does not use `api` itself
  api: [async ({ playwright }, provide) => {
    const ctx = await playwright.request.newContext({ baseURL: API })
    expect((await ctx.post('/api/scoring-config/reset')).ok()).toBeTruthy()
    expect((await ctx.post('/api/environment/reset')).ok()).toBeTruthy()
    await provide(ctx)
    await ctx.dispose()
  }, { auto: true }],
})
export { expect }

export async function openTab(page: Page, name: string) {
  await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name }).click()
}

export async function load(page: Page) {
  await page.goto('/')
  await expect(page.getByTestId('kpis')).toBeVisible()
}
