import type { Environment } from './types'

export interface Pos {
  x: number
  y: number
}

const COL = 310
const ROW = 104

const VCOL = 250
const VROW = 120

/**
 * Layered layout: layer = BFS distance from compromised assets; controls in a last layer. Mirrored for RTL.
 * `vertical` (narrow screens) stacks layers top-down so a path is a narrow column that stays legible on a phone;
 * the default is left-to-right layers (right-to-left in RTL).
 */
export function computeLayout(env: Environment, dir: 'ltr' | 'rtl', vertical = false): Record<string, Pos> {
  const out = new Map<string, string[]>()
  for (const r of env.relationships) {
    if (r.type === 'protects') continue
    out.set(r.source, [...(out.get(r.source) ?? []), r.target])
  }
  const depth = new Map<string, number>()
  const queue = env.assets.filter((a) => a.compromised).map((a) => a.id)
  queue.forEach((id) => depth.set(id, 0))
  for (let i = 0; i < queue.length; i++) {
    const id = queue[i]
    for (const n of out.get(id) ?? []) {
      if (!depth.has(n)) {
        depth.set(n, depth.get(id)! + 1)
        queue.push(n)
      }
    }
  }
  const maxDepth = Math.max(0, ...depth.values())
  const cols = new Map<number, string[]>()
  const controls: string[] = []
  for (const a of env.assets) {
    if (a.type === 'control') {
      controls.push(a.id)
      continue
    }
    const d = depth.get(a.id) ?? maxDepth + 1
    cols.set(d, [...(cols.get(d) ?? []), a.id])
  }
  const pos: Record<string, Pos> = {}
  const sign = dir === 'rtl' ? -1 : 1
  if (vertical) {
    for (const [d, ids] of cols) {
      ids.forEach((id, i) => {
        pos[id] = { x: sign * (i - (ids.length - 1) / 2) * VCOL, y: d * VROW }
      })
    }
    const lastRow = Math.max(0, ...cols.keys()) + 1
    controls.forEach((id, i) => {
      pos[id] = { x: sign * (i - (controls.length - 1) / 2) * VCOL, y: lastRow * VROW }
    })
    return pos
  }
  let tallest = 0
  for (const [d, ids] of cols) {
    tallest = Math.max(tallest, ids.length)
    ids.forEach((id, i) => {
      pos[id] = { x: sign * d * COL, y: i * ROW - ((ids.length - 1) * ROW) / 2 }
    })
  }
  controls.forEach((id, i) => {
    pos[id] = { x: sign * (i + 1) * COL, y: (tallest / 2 + 1) * ROW }
  })
  return pos
}
