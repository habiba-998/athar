import type {
  Activity, AiStatus, Analysis, Asset, AttackScenario, AuthStatus, EnvMeta, Environment, EvidenceOverview, Explanation, PlansResponse,
  RecExplanation, Recommendation, Relationship, ScoringConfig, ScoringConfigResponse, SensitivityResult, ServiceDependency,
  SimAction, SimRecord, SimResult,
} from './types'

export class ApiError extends Error {
  status: number
  /** Machine-readable error code from the API (e.g. read_only_demo), when present. */
  code: string
  constructor(message: string, status: number, code = '') {
    super(message)
    this.status = status
    this.code = code
  }
}

/**
 * Where the API lives. Empty (default) = same origin as the page (single-service deployment or the Vite dev proxy).
 * Set VITE_API_BASE to the API's public https origin for a split deployment. It is compiled into the public bundle,
 * so it must never contain a secret.
 */
export function normalizeBase(raw: string | undefined): string {
  return (raw ?? '').trim().replace(/\/+$/, '')
}
export const API_BASE = normalizeBase(import.meta.env.VITE_API_BASE as string | undefined)
export const apiUrl = (path: string, base: string = API_BASE) => `${base}${path}`

const TOKEN_KEY = 'athar.token'
export const tokenStore = {
  get(): string {
    try {
      return sessionStorage.getItem(TOKEN_KEY) ?? ''
    } catch {
      return ''
    }
  },
  set(v: string) {
    try {
      sessionStorage.setItem(TOKEN_KEY, v)
    } catch {
      // storage unavailable: token only lives for this page load
    }
  },
  clear() {
    try {
      sessionStorage.removeItem(TOKEN_KEY)
    } catch {
      // ignore
    }
  },
}

/** Turn any API error body (string detail, validation list, or {error}) into one readable string. */
export function formatDetail(body: unknown, fallback: string): string {
  if (body && typeof body === 'object') {
    const b = body as { detail?: unknown; error?: unknown }
    if (typeof b.detail === 'string') return b.detail
    if (Array.isArray(b.detail)) {
      const lines = b.detail
        .map((d) => (d && typeof d === 'object' ? `${(d as { loc?: string }).loc ? (d as { loc?: string }).loc + ': ' : ''}${(d as { msg?: string }).msg ?? ''}` : String(d)))
        .filter(Boolean)
      if (lines.length) return lines.join('\n')
    }
    if (typeof b.error === 'string') return b.error
  }
  return fallback
}

/**
 * STATIC build (`vite build --mode static`): there is no server. The unchanged Python backend runs inside the browser (Pyodide in a
 * Web Worker) and API calls are answered by it. Otherwise: an ordinary fetch to the API origin.
 */
export const STATIC_MODE = import.meta.env.MODE === 'static'

async function transport(path: string, init: RequestInit | undefined, headers: Record<string, string>) {
  if (STATIC_MODE) {
    const { inBrowserRequest } = await import('./inbrowser/client')
    const r = await inBrowserRequest(path, { method: init?.method, headers, body: typeof init?.body === 'string' ? init.body : null })
    return { ok: r.status >= 200 && r.status < 300, status: r.status, json: async () => JSON.parse(r.body) as unknown }
  }
  return fetch(apiUrl(path), { ...init, headers })
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { 'content-type': 'application/json' }
  const t = tokenStore.get()
  if (t) headers['x-athar-token'] = t
  const r = await transport(path, init, headers)
  if (!r.ok) {
    let body: unknown = null
    try {
      body = await r.json()
    } catch {
      // non-JSON error body
    }
    const code = body && typeof body === 'object' && typeof (body as { error?: unknown }).error === 'string' ? (body as { error: string }).error : ''
    throw new ApiError(formatDetail(body, `HTTP ${r.status}`), r.status, code)
  }
  return r.json() as Promise<T>
}

const json = (method: string, body?: unknown): RequestInit => ({ method, body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  authStatus: () => req<AuthStatus>('/api/auth/status'),
  whoami: () => req<{ can_write: boolean }>('/api/auth/whoami'),
  aiStatus: () => req<AiStatus>('/api/ai/status'),
  environment: () => req<Environment>('/api/environment'),
  envMeta: () => req<EnvMeta>('/api/environment/meta'),
  analysis: () => req<Analysis>('/api/analysis'),
  recommendations: () => req<Recommendation[]>('/api/recommendations'),
  activity: () => req<Activity[]>('/api/activity'),
  simulations: () => req<SimRecord[]>('/api/simulations'),
  simulationRecord: (id: number) => req<SimResult>(`/api/simulations/${id}`),
  simulate: (actions: SimAction[]) => req<SimResult>('/api/simulate', json('POST', { actions })),
  explain: (kind: 'path' | 'recommendation', id: string, lang: 'en' | 'ar') =>
    req<Explanation>('/api/explain', json('POST', { kind, id, lang })),
  recExplanation: (id: string) => req<RecExplanation>(`/api/recommendations/${encodeURIComponent(id)}/explanation`),
  plans: () => req<PlansResponse>('/api/plans'),
  planReport: (id: string, lang: 'en' | 'ar') => req<{ markdown: string }>(`/api/plans/${encodeURIComponent(id)}/report?lang=${lang}`),
  scoringConfig: () => req<ScoringConfigResponse>('/api/scoring-config'),
  setScoringConfig: (c: ScoringConfig) => req<ScoringConfigResponse>('/api/scoring-config', json('PUT', c)),
  resetScoringConfig: () => req<ScoringConfigResponse>('/api/scoring-config/reset', json('POST')),
  sensitivity: (trials?: number, spread?: number) =>
    req<SensitivityResult>(`/api/sensitivity${trials !== undefined ? `?trials=${trials}&spread=${spread ?? 0.3}` : ''}`),
  evidence: () => req<EvidenceOverview>('/api/evidence'),
  services: () => req<ServiceDependency[]>('/api/services'),
  attackScenarios: () => req<AttackScenario[]>('/api/attack-scenarios'),
  activateScenario: (id: string) => req<EnvMeta>(`/api/attack-scenarios/${encodeURIComponent(id)}/activate`, json('POST')),
  importEnv: (env: unknown) => req<EnvMeta>('/api/environment', json('PUT', env)),
  resetEnv: () => req<EnvMeta>('/api/environment/reset', json('POST')),
  undoEnv: () => req<EnvMeta>('/api/environment/undo', json('POST')),
  createAsset: (a: Asset) => req<EnvMeta>('/api/assets', json('POST', a)),
  updateAsset: (a: Asset) => req<EnvMeta>(`/api/assets/${encodeURIComponent(a.id)}`, json('PUT', a)),
  deleteAsset: (id: string) => req<EnvMeta>(`/api/assets/${encodeURIComponent(id)}?cascade=true`, json('DELETE')),
  createRel: (r: Relationship) => req<EnvMeta>('/api/relationships', json('POST', r)),
  updateRel: (r: Relationship) => req<EnvMeta>(`/api/relationships/${encodeURIComponent(r.id)}`, json('PUT', r)),
  deleteRel: (id: string) => req<EnvMeta>(`/api/relationships/${encodeURIComponent(id)}`, json('DELETE')),
}
