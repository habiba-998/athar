import type { Analysis, Asset, AttackPath, Environment, Relationship, Severity, SimAction } from './types'

type T = (key: string, params?: Record<string, string | number>) => string
type Name = (a: Asset | undefined) => string

export const findAsset = (env: Environment, id: string) => env.assets.find((a) => a.id === id)
export const findRel = (env: Environment, id: string) => env.relationships.find((r) => r.id === id)

/** Score bands used for labelling scales only; the authoritative bands live in the backend (analysis.SEVERITY_BANDS). */
export const BANDS: { min: number; severity: Severity }[] = [
  { min: 70, severity: 'critical' },
  { min: 50, severity: 'high' },
  { min: 30, severity: 'medium' },
]

export function relText(env: Environment, r: Relationship, t: T, name: Name): string {
  return `${name(findAsset(env, r.source))} ${t(`rel.${r.type}`)} ${name(findAsset(env, r.target))}`
}

export function actionText(a: SimAction, env: Environment, t: T, name: Name): string {
  if ('relationship_id' in a) {
    const r = findRel(env, a.relationship_id)
    return `${t(`action.${a.kind}`)}: ${r ? relText(env, r, t, name) : a.relationship_id}`
  }
  return `${t(`action.${a.kind}`)}: ${name(findAsset(env, a.asset_id))}`
}

export const actionKey = (a: SimAction) => `${a.kind}:${'relationship_id' in a ? a.relationship_id : a.asset_id}`

export function routeNames(env: Environment, nodes: string[], name: Name): string[] {
  return nodes.map((n) => name(findAsset(env, n)))
}

export function pathRoute(env: Environment, nodes: string[], name: Name, arrow = '→'): string {
  return routeNames(env, nodes, name).join(`  ${arrow}  `)
}

export const pathEvidence = (p: AttackPath): string[] => p.steps.map((s) => s.evidence)

export interface RiskedAsset {
  asset: Asset
  paths: number
  worst: AttackPath
}

/** Sensitive assets reached by at least one attack path, ranked by their worst path. Pure aggregation of API data. */
export function assetsAtRisk(analysis: Analysis, env: Environment): RiskedAsset[] {
  const byTarget = new Map<string, RiskedAsset>()
  for (const p of analysis.paths) {
    const asset = findAsset(env, p.target)
    if (!asset) continue
    const cur = byTarget.get(p.target)
    if (!cur) byTarget.set(p.target, { asset, paths: 1, worst: p })
    else {
      cur.paths += 1
      if (p.score > cur.worst.score) cur.worst = p
    }
  }
  return [...byTarget.values()].sort((a, b) => b.worst.score - a.worst.score || a.asset.id.localeCompare(b.asset.id))
}

export function pathsById(paths: AttackPath[] | undefined): Map<string, AttackPath> {
  return new Map((paths ?? []).map((p) => [p.id, p]))
}
