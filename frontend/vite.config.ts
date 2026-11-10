import fs from 'node:fs'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const api = process.env.ATHAR_API_URL ?? 'http://127.0.0.1:8000'
// Security headers of the static (in-browser engine) build: one source for the Netlify `_headers` file and for `vite preview`.
const staticHeaders = JSON.parse(fs.readFileSync(new URL('./static-headers.json', import.meta.url), 'utf8')) as Record<string, string>

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  // static build: no server, so relative URLs work from any path (a Netlify site, a GitHub Pages sub-path, a local folder)
  base: mode === 'static' ? './' : '/',
  publicDir: mode === 'static' ? 'static-assets' : false,
  worker: { format: 'es' },
  build: { assetsInlineLimit: 0 },   // fonts stay real files, so the strict CSP (font-src 'self', no data:) never blocks them
  server: { port: 5173, proxy: { '/api': api } },
  preview: { headers: staticHeaders },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
}))
