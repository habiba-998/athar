import { describe, expect, it } from 'vitest'
import { formatDetail, tokenStore } from './api'

describe('formatDetail', () => {
  it('uses a string detail as-is', () => {
    expect(formatDetail({ detail: 'nothing to undo' }, 'x')).toBe('nothing to undo')
  })
  it('formats FastAPI/pydantic validation lists with their location', () => {
    expect(formatDetail({ detail: [{ loc: 'relationships.0', msg: 'Value error, unknown asset' }, { loc: '', msg: 'bad' }] }, 'x'))
      .toBe('relationships.0: Value error, unknown asset\nbad')
  })
  it('falls back to {error} codes and then to the fallback text', () => {
    expect(formatDetail({ error: 'rate_limited' }, 'x')).toBe('rate_limited')
    expect(formatDetail({}, 'HTTP 500')).toBe('HTTP 500')
    expect(formatDetail(null, 'HTTP 502')).toBe('HTTP 502')
    expect(formatDetail({ detail: [] }, 'HTTP 422')).toBe('HTTP 422')
  })
  it('never throws on odd shapes', () => {
    expect(() => formatDetail({ detail: [null, 5, 'x'] }, 'f')).not.toThrow()
    expect(formatDetail('plain string', 'f')).toBe('f')
  })
})

describe('tokenStore without browser storage', () => {
  it('degrades to an empty token instead of throwing', () => {
    expect(tokenStore.get()).toBe('')
    expect(() => { tokenStore.set('t'); tokenStore.clear() }).not.toThrow()
  })
})

describe('API base URL', () => {
  it('is empty by default, so the app talks to its own origin', async () => {
    const { API_BASE, apiUrl } = await import('./api')
    expect(API_BASE).toBe('')
    expect(apiUrl('/api/health')).toBe('/api/health')
  })
  it('normalises a configured base: trims and drops trailing slashes', async () => {
    const { normalizeBase, apiUrl } = await import('./api')
    expect(normalizeBase(undefined)).toBe('')
    expect(normalizeBase('  https://api.example.org// ')).toBe('https://api.example.org')
    expect(apiUrl('/api/health', 'https://api.example.org')).toBe('https://api.example.org/api/health')
  })
})
