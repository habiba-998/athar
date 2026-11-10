/** Main-thread side of the in-browser backend: sends API calls to the Pyodide worker and returns Response-like results. */
type Listener = (text: string) => void
type Reply = { status: number; headers: Record<string, string>; body: string }

let worker: Worker | null = null
let seq = 0
const pending = new Map<number, (r: Reply) => void>()
const listeners = new Set<Listener>()
let bootError = ''
let readyResolve: () => void = () => undefined
let readyReject: (e: Error) => void = () => undefined
const ready = new Promise<void>((res, rej) => { readyResolve = res; readyReject = rej })
ready.catch(() => undefined)                       // reported through inBrowserRequest; avoid an unhandled-rejection warning

export const onEngineStatus = (fn: Listener) => { listeners.add(fn); return () => { listeners.delete(fn) } }

function start(): Worker {
  if (worker) return worker
  worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' })
  worker.onmessage = (ev: MessageEvent) => {
    const m = ev.data
    if (m.type === 'status') listeners.forEach((l) => l(m.text))
    else if (m.type === 'ready') readyResolve()
    else if (m.type === 'error') { bootError = m.text; readyReject(new Error(m.text)) }
    else if (m.type === 'response') { pending.get(m.id)?.(m); pending.delete(m.id) }
  }
  worker.onerror = (e) => { bootError = e.message || 'worker failed'; readyReject(new Error(bootError)) }
  worker.postMessage({ type: 'boot' })
  return worker
}

export async function inBrowserRequest(path: string, init: { method?: string; headers?: Record<string, string>; body?: string | null }): Promise<Reply> {
  const w = start()
  try {
    await ready
  } catch {
    throw new Error(`The in-browser analysis engine could not start: ${bootError}`)
  }
  const id = ++seq
  return new Promise<Reply>((resolve) => {
    pending.set(id, resolve)
    w.postMessage({ id, method: init.method ?? 'GET', url: path, headers: init.headers ?? {}, body: init.body ?? null })
  })
}

/** Start loading before the first API call so the splash screen can show progress. */
export const warmUp = () => { start() }
