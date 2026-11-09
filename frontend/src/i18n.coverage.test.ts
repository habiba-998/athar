import { readFileSync, readdirSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { messages } from './messages'

const files = readdirSync(__dirname).filter((f) => /\.tsx?$/.test(f) && !f.endsWith('.test.ts'))

describe('translations', () => {
  it('every literal t("key") used in the UI exists in English and Arabic', () => {
    const missing: string[] = []
    for (const f of files) {
      const src = readFileSync(`${__dirname}/${f}`, 'utf-8')
      for (const m of src.matchAll(/\bt\(\s*['"]([a-zA-Z0-9_.]+)['"]/g)) {
        const k = m[1]
        if (k.endsWith('.')) continue          // a prefix concatenated with a variable (t('sev.' + x)); the families test covers those
        if (!(k in messages.en) || !(k in messages.ar)) missing.push(`${f}: ${k}`)
      }
    }
    expect(missing).toEqual([])
  })
  it('every dynamic key family used with a template literal has all its members in both languages', () => {
    const families: [string, string[]][] = [
      ['plan.', ['status_quo', 'minimal', 'business_safe', 'reversible', 'balanced', 'max_reduction', 'min_cut']],
      ['effect.', ['interrupted', 'degraded', 'friction']], ['recovery.', ['rollback', 'reprovision', 'unknown']],
      ['rto.', ['within', 'exceeds', 'unknown', 'not_applicable']], ['role.', ['security_owner', 'service_owner', 'change_board']],
      ['val.', ['none', 'synthetic_exercise', 'real_world']], ['conf.', ['high', 'medium', 'low']], ['stab.', ['stable', 'moderate', 'sensitive']],
      ['ind.', ['low', 'medium', 'high']], ['cls.', ['validated', 'observed', 'inferred', 'theoretical']], ['ev.def.', ['validated', 'observed', 'inferred', 'theoretical']],
      ['type.', ['user', 'service_account', 'group', 'server', 'database', 'cloud', 'identity_provider', 'control']],
      ['why.', ['every_change_requires_human_approval', 'services_affected', 'business_critical_access', 'legitimate_access_lost', 'high_operational_impact', 'not_fully_reversible', 'recovery_vs_rto']],
      ['cfg.', ['evidence_observed', 'evidence_inferred', 'evidence_theoretical', 'privilege_read', 'privilege_write', 'mfa_factor', 'length_penalty', 'exposure_bonus']],
    ]
    for (const [prefix, names] of families) for (const n of names) {
      expect(`${prefix}${n}` in messages.en, `en ${prefix}${n}`).toBe(true)
      expect(`${prefix}${n}` in messages.ar, `ar ${prefix}${n}`).toBe(true)
    }
  })
  it('Arabic strings are real Arabic, not copies of the English', () => {
    const same = Object.keys(messages.en).filter((k) => messages.en[k as keyof typeof messages.en] === messages.ar[k as keyof typeof messages.ar] && /[a-z]{4}/.test(messages.en[k as keyof typeof messages.en]))
    // brand names and units may legitimately stay Latin; anything else must be translated
    expect(same.filter((k) => !/^(app\.|lang\.|chip\.ai)/.test(k))).toEqual([])
  })
})
