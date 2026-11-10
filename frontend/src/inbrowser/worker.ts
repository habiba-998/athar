/// <reference lib="webworker" />
// Web Worker that hosts the Python backend (Pyodide). Everything is self-hosted under ../pyodide/: no third-party CDN is contacted.
import { loadPyodide, type PyodideInterface } from 'pyodide'
import bridge from './bridge.py?raw'

const base = new URL('../pyodide/', import.meta.url).href
let ready: Promise<PyodideInterface> | null = null

const say = (text: string) => postMessage({ type: 'status', text })

function boot(): Promise<PyodideInterface> {
  ready ??= (async () => {
    say('Loading the Python runtime')
    const py = await loadPyodide({ indexURL: base, lockFileURL: base + 'pyodide-lock.json' })
    say('Loading the analysis libraries')
    await py.loadPackage(['pydantic', 'networkx', 'starlette', 'fastapi', 'anyio'])
    say('Loading the ATHAR engine')
    const { files } = (await (await fetch(base + 'athar-backend.json')).json()) as { files: Record<string, string> }
    for (const [rel, text] of Object.entries(files)) {
      const target = `/home/pyodide/backend/app/${rel}`
      py.FS.mkdirTree(target.slice(0, target.lastIndexOf('/')))
      py.FS.writeFile(target, text)
    }
    py.runPython(bridge)
    py.globals.get('install')('/home/pyodide/backend')
    say('Ready')
    return py
  })()
  return ready
}

interface Req { id: number; method: string; url: string; headers: Record<string, string>; body: string | null }

self.onmessage = async (ev: MessageEvent<Req | { type: 'boot' }>) => {
  const msg = ev.data
  try {
    const py = await boot()
    if ('type' in msg) return postMessage({ type: 'ready' })
    const handle = py.globals.get('handle')
    const out = JSON.parse(await handle(msg.method, msg.url, JSON.stringify(msg.headers), msg.body)) as { status: number; headers: Record<string, string>; body: string }
    postMessage({ type: 'response', id: msg.id, ...out })
  } catch (e) {
    if ('type' in msg) return postMessage({ type: 'error', text: String(e) })
    postMessage({ type: 'response', id: msg.id, status: 500, headers: {}, body: JSON.stringify({ error: 'engine_error', detail: String(e).slice(0, 300) }) })
  }
}
