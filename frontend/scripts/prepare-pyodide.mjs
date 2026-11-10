// Prepares the self-hosted Python-in-the-browser runtime for the STATIC build (`npm run build:static`).
//
// What it produces in static-assets/pyodide/ (git-ignored, regenerated on every static build):
//   * the Pyodide core (WebAssembly + standard library) copied from the pinned npm package
//   * only the Python wheels ATHAR needs (pydantic, pydantic_core, FastAPI, Starlette, NetworkX and their small dependencies),
//     downloaded from the official Pyodide distribution of the SAME version and verified against the sha256 in its lock file
//   * a trimmed pyodide-lock.json listing just those packages (NetworkX's optional NumPy/Matplotlib stack is dropped: ATHAR does
//     not use it), so the browser never fetches anything from a third-party CDN at run time
//   * athar-backend.json: the backend source (backend/app/**/*.py), so the browser runs EXACTLY the code in this repository
import { createHash } from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..')
const npmDir = path.join(root, 'node_modules', 'pyodide')
const outDir = path.join(root, 'static-assets', 'pyodide')
const cacheDir = path.join(root, 'node_modules', '.cache', 'athar-pyodide')
const version = JSON.parse(fs.readFileSync(path.join(npmDir, 'package.json'), 'utf8')).version
const CDN = `https://cdn.jsdelivr.net/pyodide/v${version}/full/`

const ROOTS = ['fastapi', 'starlette', 'pydantic', 'networkx', 'anyio']
// optional / unused dependencies that the lock file declares but ATHAR never imports
const DROP = { networkx: ['decorator', 'setuptools', 'matplotlib', 'numpy'], fastapi: ['httpx', 'jinja2'] }
const norm = (n) => n.toLowerCase().replace(/_/g, '-')

const lock = JSON.parse(fs.readFileSync(path.join(npmDir, 'pyodide-lock.json'), 'utf8'))
const byNorm = new Map(Object.entries(lock.packages).map(([k, v]) => [norm(k), [k, v]]))
const needed = new Map()
const visit = (name) => {
  const hit = byNorm.get(norm(name))
  if (!hit) throw new Error(`package ${name} is not in the Pyodide ${version} lock file`)
  const [key, pkg] = hit
  if (needed.has(key)) return
  const depends = (pkg.depends ?? []).filter((d) => !(DROP[key] ?? []).includes(d))
  needed.set(key, { ...pkg, depends })
  depends.forEach(visit)
}
ROOTS.forEach(visit)

fs.rmSync(outDir, { recursive: true, force: true })
fs.mkdirSync(outDir, { recursive: true })
fs.mkdirSync(cacheDir, { recursive: true })

for (const f of ['pyodide.asm.mjs', 'pyodide.asm.wasm', 'python_stdlib.zip']) fs.copyFileSync(path.join(npmDir, f), path.join(outDir, f))

const sha = (buf) => createHash('sha256').update(buf).digest('hex')
let bytes = 0
for (const [key, pkg] of needed) {
  const cached = path.join(cacheDir, pkg.file_name)
  let buf = fs.existsSync(cached) ? fs.readFileSync(cached) : null
  if (!buf || sha(buf) !== pkg.sha256) {
    const r = await fetch(CDN + pkg.file_name)
    if (!r.ok) throw new Error(`download of ${pkg.file_name} failed: HTTP ${r.status}`)
    buf = Buffer.from(await r.arrayBuffer())
    if (sha(buf) !== pkg.sha256) throw new Error(`checksum mismatch for ${pkg.file_name}`)
    fs.writeFileSync(cached, buf)
  }
  fs.writeFileSync(path.join(outDir, pkg.file_name), buf)
  bytes += buf.length
  console.log(`  ${key.padEnd(18)} ${pkg.file_name} (${(buf.length / 1024).toFixed(0)} kB)`)
}
fs.writeFileSync(path.join(outDir, 'pyodide-lock.json'), JSON.stringify({ info: lock.info, packages: Object.fromEntries(needed) }))

// the backend source, verbatim
const files = {}
const walk = (dir, rel = '') => {
  for (const e of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    if (e.name === '__pycache__') continue
    const p = path.join(dir, e.name), r = rel ? `${rel}/${e.name}` : e.name
    if (e.isDirectory()) walk(p, r)
    else if (e.name.endsWith('.py')) files[r] = fs.readFileSync(p, 'utf8')
  }
}
walk(path.resolve(root, '..', 'backend', 'app'))
fs.writeFileSync(path.join(outDir, 'athar-backend.json'), JSON.stringify({ files }))
console.log(`pyodide ${version}: ${needed.size} packages, ${(bytes / 1048576).toFixed(1)} MB of wheels, ${Object.keys(files).length} backend files -> static-assets/pyodide`)
