import { defineConfig } from '@playwright/test'

// Runs the static-site browser checks against an ALREADY DEPLOYED site (no local servers):
//   $env:ATHAR_STATIC_URL = "https://<your-site>"; npx playwright test -c playwright.external.config.ts
const url = process.env.ATHAR_STATIC_URL
if (!url) throw new Error('set ATHAR_STATIC_URL to the deployed https address')

export default defineConfig({
  testDir: './tests',
  testMatch: 'static.spec.ts',
  timeout: 180_000,
  workers: 1,
  reporter: [['list']],
  use: { baseURL: url, trace: 'retain-on-failure' },
})
