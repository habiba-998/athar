// Writes dist-static/_headers (Netlify format) from static-headers.json, plus long-lived caching for content-hashed and runtime files.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const headers = JSON.parse(fs.readFileSync(path.join(root, 'static-headers.json'), 'utf8'))
const block = (rules) => Object.entries(rules).map(([k, v]) => `  ${k}: ${v}`).join('\n')
const text = [
  '/*', block(headers), '',
  '/assets/*', block({ 'Cache-Control': 'public, max-age=31536000, immutable' }), '',
  '/pyodide/*', block({ 'Cache-Control': 'public, max-age=31536000, immutable' }), '',
  '/', block({ 'Cache-Control': 'no-cache' }), '',
].join('\n')
fs.writeFileSync(path.join(root, 'dist-static', '_headers'), text)
console.log('wrote dist-static/_headers')
