import { describe, expect, it } from 'vitest'
import { actionKey } from './helpers'
import { computeLayout } from './layout'
import { messages } from './messages'
import { translate } from './i18n'
import type { Environment } from './types'

const env = {
  name: 't',
  synthetic: true,
  assets: [
    { id: 'a', compromised: true, type: 'user' },
    { id: 'b', compromised: false, type: 'server' },
    { id: 'c', compromised: false, type: 'database' },
    { id: 'x', compromised: false, type: 'control' },
  ],
  relationships: [
    { id: 'r1', source: 'a', target: 'b', type: 'can_login' },
    { id: 'r2', source: 'b', target: 'c', type: 'read_access' },
    { id: 'r3', source: 'x', target: 'b', type: 'protects' },
  ],
} as unknown as Environment

describe('layout', () => {
  it('places assets in columns by distance from the compromised asset', () => {
    const p = computeLayout(env, 'ltr')
    expect(p.a.x).toBe(0)
    expect(p.b.x).toBeGreaterThan(p.a.x)
    expect(p.c.x).toBeGreaterThan(p.b.x)
  })
  it('stacks layers top-down in the vertical (phone) layout, and still mirrors for RTL', () => {
    const v = computeLayout(env, 'ltr', true)
    expect(v.a.y).toBe(0)
    expect(v.b.y).toBeGreaterThan(v.a.y)
    expect(v.c.y).toBeGreaterThan(v.b.y)
    expect(new Set([v.a.x, v.b.x, v.c.x]).size).toBe(1)          // a chain is a single column
    expect(v.x.y).toBeGreaterThan(v.c.y)                          // controls sit below everything
    const ids = Object.keys(v)
    expect(new Set(ids.map((i) => `${v[i].x},${v[i].y}`)).size).toBe(ids.length) // no overlapping nodes
    expect(computeLayout(env, 'rtl', true).c.y).toBe(v.c.y)
  })
  it('mirrors horizontally for RTL', () => {
    const l = computeLayout(env, 'ltr')
    const r = computeLayout(env, 'rtl')
    expect(r.c.x).toBe(-l.c.x)
  })
})

describe('i18n', () => {
  it('has identical key sets for English and Arabic with no empty strings', () => {
    expect(Object.keys(messages.ar).sort()).toEqual(Object.keys(messages.en).sort())
    for (const lang of ['en', 'ar'] as const) {
      for (const v of Object.values(messages[lang])) expect(v.trim()).not.toBe('')
    }
  })
  it('interpolates parameters in both languages', () => {
    expect(translate('en', 'finding.attack_path', { target: 'DB' })).toContain('DB')
    expect(translate('ar', 'finding.attack_path', { target: 'DB' })).toContain('DB')
  })
  it('falls back to the key for unknown messages', () => {
    expect(translate('en', 'nope.key')).toBe('nope.key')
  })
})

describe('helpers', () => {
  it('builds stable action keys', () => {
    expect(actionKey({ kind: 'remove_relationship', relationship_id: 'r1' })).toBe('remove_relationship:r1')
    expect(actionKey({ kind: 'apply_mfa', asset_id: 'b' })).toBe('apply_mfa:b')
  })
})
