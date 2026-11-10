import { defineConfig } from '@playwright/test'
import os from 'node:os'
import path from 'node:path'

// E2E runs against its own backend/frontend on dedicated ports with a throw-away database,
// so it never touches a dev server or the dev database. Set ATHAR_PYTHON to a Python with the backend requirements.
const python = process.env.ATHAR_PYTHON ?? 'python'
const backendDir = path.resolve(process.cwd(), '../backend') // run from the frontend directory
const API_PORT = 8100
const WEB_PORT = 5183
const DEMO_API_PORT = 8101
const DEMO_WEB_PORT = 5184
export const DEMO_ADMIN_TOKEN = 'e2e-admin-token-0123456789-abcdef'
const e2eDb = path.join(os.tmpdir(), `athar-e2e-${process.pid}.db`)
const demoDb = path.join(os.tmpdir(), `athar-e2e-demo-${process.pid}.db`)

export default defineConfig({
  testDir: './tests',
  timeout: 45_000,
  workers: 1, // tests share one backend state; they reset it in beforeEach
  reporter: [['list']],
  use: { baseURL: `http://127.0.0.1:${WEB_PORT}`, trace: 'retain-on-failure' },
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:app --port ${API_PORT}`,
      cwd: backendDir,
      url: `http://127.0.0.1:${API_PORT}/api/health`,
      reuseExistingServer: false,
      env: { ATHAR_DB: e2eDb, ATHAR_RATE_READ: '5000', ATHAR_RATE_WRITE: '5000', ATHAR_RATE_EXPLAIN: '5000' },
    },
    {
      command: `npx vite --host 127.0.0.1 --port ${WEB_PORT} --strictPort`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: false,
      env: { ATHAR_API_URL: `http://127.0.0.1:${API_PORT}` },
    },
    {
      // the public read-only demo: its own backend (ATHAR_MODE=demo) and frontend
      command: `"${python}" -m uvicorn app.main:app --port ${DEMO_API_PORT}`,
      cwd: backendDir,
      url: `http://127.0.0.1:${DEMO_API_PORT}/api/health`,
      reuseExistingServer: false,
      env: { ATHAR_DB: demoDb, ATHAR_MODE: 'demo', ATHAR_ADMIN_TOKEN: DEMO_ADMIN_TOKEN, ATHAR_RATE_READ: '5000', ATHAR_RATE_WRITE: '5000', ATHAR_RATE_EXPLAIN: '5000' },
    },
    {
      // the STATIC build (no server: the Python backend runs in the browser), served with the production security headers
      command: 'npm run build:static && npm run preview:static',
      url: 'http://127.0.0.1:5185',
      timeout: 300_000,
      reuseExistingServer: false,
    },
    {
      command: `npx vite --host 127.0.0.1 --port ${DEMO_WEB_PORT} --strictPort`,
      url: `http://127.0.0.1:${DEMO_WEB_PORT}`,
      reuseExistingServer: false,
      env: { ATHAR_API_URL: `http://127.0.0.1:${DEMO_API_PORT}` },
    },
  ],
})
