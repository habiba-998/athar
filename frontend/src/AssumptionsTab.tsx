import { useEffect, useState } from 'react'
import { api } from './api'
import { useI18n } from './i18n'
import { Icon } from './icons'
import { useMode } from './mode'
import type { ScoringConfig, ScoringConfigResponse, SensitivityResult } from './types'
import { Button, Field, Id, Panel, Spinner, controlCls } from './ui'

const FIELDS: { key: keyof ScoringConfig; min: number; max: number; step: number }[] = [
  { key: 'evidence_observed', min: 0.05, max: 1, step: 0.01 },
  { key: 'evidence_inferred', min: 0.05, max: 1, step: 0.01 },
  { key: 'evidence_theoretical', min: 0.05, max: 1, step: 0.01 },
  { key: 'privilege_read', min: 0.05, max: 1, step: 0.01 },
  { key: 'privilege_write', min: 0.05, max: 1, step: 0.01 },
  { key: 'mfa_factor', min: 0.05, max: 1, step: 0.01 },
  { key: 'length_penalty', min: 0, max: 0.5, step: 0.01 },
  { key: 'exposure_bonus', min: 1, max: 1.5, step: 0.01 },
]

/** Local mirror of the server's rules so the user sees the problem before sending; the server still validates. */
export function configProblems(c: ScoringConfig): string[] {
  const out: string[] = []
  for (const f of FIELDS) {
    const v = c[f.key]
    if (!Number.isFinite(v) || v < f.min || v > f.max) out.push(`range:${f.key}`)
  }
  if (!(c.evidence_theoretical <= c.evidence_inferred && c.evidence_inferred <= c.evidence_observed)) out.push('order:evidence')
  if (!(c.privilege_read <= c.privilege_write)) out.push('order:privilege')
  return out
}

export default function AssumptionsTab({ onConfigChanged }: { onConfigChanged: () => Promise<void> }) {
  const { t } = useI18n()
  return (
    <div className="space-y-4">
      <p className="flex gap-2 rounded-lg border border-hairline-2 bg-raised/50 p-3 text-sm text-mist"><Icon name="info" size={16} className="mt-0.5 text-teal" />{t('asm.honesty')}</p>
      <ConfigPanel onChanged={onConfigChanged} />
      <SensitivityPanel />
    </div>
  )
}

function ConfigPanel({ onChanged }: { onChanged: () => Promise<void> }) {
  const { t } = useI18n()
  const { readOnly } = useMode()
  const [cfg, setCfg] = useState<ScoringConfigResponse | null>(null)
  const [draft, setDraft] = useState<ScoringConfig | null>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => { api.scoringConfig().then((c) => { setCfg(c); setDraft(c.config) }).catch((e) => setMsg({ ok: false, text: String(e.message ?? e) })) }, [])
  if (!cfg || !draft) return <Spinner label={t('state.loading')} />

  const problems = configProblems(draft)
  const dirty = JSON.stringify(draft) !== JSON.stringify(cfg.config)
  const apply = async (fn: () => Promise<ScoringConfigResponse>, ok: string) => {
    setBusy(true)
    setMsg(null)
    try {
      const c = await fn()
      setCfg(c)
      setDraft(c.config)
      await onChanged()
      setMsg({ ok: true, text: ok })
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel title={t('asm.config')} hint={t('asm.config.hint')}>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" data-testid="scoring-config">
        {FIELDS.map((f) => {
          const bad = problems.some((p) => p === `range:${f.key}`)
          return (
            <Field key={f.key} label={t(`cfg.${f.key}`)} hint={`${t('asm.default')}: ${cfg.defaults[f.key]}`} error={bad ? t('asm.err.range', { min: f.min, max: f.max }) : undefined}>
              {({ id, describedBy, invalid }) => (
                <input id={id} aria-describedby={describedBy} aria-invalid={invalid} type="number" inputMode="decimal" min={f.min} max={f.max} step={f.step} dir="ltr"
                  className={controlCls} value={Number.isFinite(draft[f.key]) ? draft[f.key] : ''} disabled={readOnly || busy}
                  onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value === '' ? Number.NaN : Number(e.target.value) })} />
              )}
            </Field>
          )
        })}
      </div>
      {problems.includes('order:evidence') && <p role="alert" className="mt-3 text-sm text-crit-fg">{t('asm.err.evidenceOrder')}</p>}
      {problems.includes('order:privilege') && <p role="alert" className="mt-3 text-sm text-crit-fg">{t('asm.err.privilegeOrder')}</p>}
      <p className="mt-3 text-xs text-faint">{t('asm.anchors')}</p>
      {readOnly && <p className="mt-3 rounded-md border border-hairline-2 p-2.5 text-sm text-mist" data-testid="config-readonly">{t('demo.readonly.note')}</p>}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="primary" disabled={readOnly || busy || !dirty || problems.length > 0} onClick={() => void apply(() => api.setScoringConfig(draft), t('asm.applied'))} data-testid="config-apply">{t('asm.apply')}</Button>
        <Button disabled={readOnly || busy || cfg.is_default} onClick={() => void apply(() => api.resetScoringConfig(), t('asm.resetDone'))} data-testid="config-reset">{t('asm.reset')}</Button>
        <span className="text-xs text-faint">{cfg.is_default ? t('asm.isDefault') : t('asm.isCustom')} · <Id>{cfg.hash}</Id></span>
      </div>
      {msg && <p role={msg.ok ? 'status' : 'alert'} className={`mt-3 text-sm ${msg.ok ? 'text-teal' : 'text-crit-fg'}`}>{msg.text}</p>}
    </Panel>
  )
}

function SensitivityPanel() {
  const { t, num } = useI18n()
  const [spread, setSpread] = useState(0.3)
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<SensitivityResult | null>(null)
  const [err, setErr] = useState('')

  const run = async () => {
    setBusy(true)
    setErr('')
    try {
      setRes(await api.sensitivity(16, spread))
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  const maxSwing = Math.max(1, ...(res?.parameters.map((p) => p.posture_swing) ?? [1]))

  return (
    <Panel title={t('sens.title')} hint={t('sens.hint')}>
      <div className="flex flex-wrap items-end gap-3">
        <Field label={t('sens.spread')}>
          {({ id }) => (
            <select id={id} className={`${controlCls} !w-auto`} value={spread} onChange={(e) => setSpread(Number(e.target.value))} data-testid="sens-spread">
              {[0.1, 0.2, 0.3, 0.5].map((s) => <option key={s} value={s}>±{Math.round(s * 100)}%</option>)}
            </select>
          )}
        </Field>
        <Button variant="primary" icon="flask" disabled={busy} onClick={() => void run()} data-testid="sens-run">{busy ? t('sens.running') : t('sens.run')}</Button>
        <span className="text-xs text-faint">{t('sens.time')}</span>
      </div>
      {err && <p role="alert" className="mt-3 text-sm text-crit-fg">{err}</p>}
      {res && (
        <div className="mt-5 space-y-6" data-testid="sens-result">
          <div className="grid gap-3 sm:grid-cols-3">
            <Kpi label={t('sens.postureRange')} value={`${num(res.posture.min)} – ${num(res.posture.max)}`} sub={`${t('sens.baseline')} ${num(res.posture.baseline)}`} />
            <Kpi label={t('sens.topRecStable')} value={`${num(res.top_recommendation_unchanged_pct)}%`} sub={t('sens.ofTrials', { n: res.trials })} />
            <Kpi label={t('sens.topPathStable')} value={`${num(res.highest_path_unchanged_pct)}%`} sub={t('sens.ofTrials', { n: res.trials })} />
          </div>
          <p className="text-xs text-faint">{t('sens.notProbability')}</p>

          <div>
            <h3 className="mb-2 text-sm font-semibold">{t('sens.influence')}</h3>
            <ul className="space-y-2">
              {res.parameters.map((p) => (
                <li key={p.name}>
                  <div className="flex items-baseline justify-between gap-2 text-sm"><span className="text-mist">{t(`cfg.${p.name}`)}</span><span className="tnum font-mono text-xs" dir="ltr">±{p.posture_swing}</span></div>
                  <div className="mt-1 h-2 rounded-sm bg-hairline"><div className="h-full rounded-sm bg-teal/80" style={{ width: `${(100 * p.posture_swing) / maxSwing}%` }} /></div>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h3 className="mb-2 text-sm font-semibold">{t('sens.recs')}</h3>
            <ul className="space-y-1.5" data-testid="sens-recs">
              {res.recommendations.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-2 rounded-md bg-raised/60 p-2 text-sm">
                  <span className="tnum font-mono text-xs text-faint">#{r.baseline_rank}</span>
                  <Id>{r.id}</Id>
                  <span className="text-xs text-mist">{t('sens.rankRange')}: {r.rank_min ?? '—'}–{r.rank_max ?? '—'} · {t('sens.top3')}: {num(r.top3_pct)}%</span>
                  <span className={`ms-auto rounded border px-1.5 py-0.5 text-xs ${r.stability === 'stable' ? 'border-low/45 text-low-fg' : r.stability === 'moderate' ? 'border-med/45 text-med-fg' : 'border-crit/45 text-crit-fg'}`}>{t(`stab.${r.stability}`)}</span>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h3 className="mb-2 text-sm font-semibold">{t('sens.paths')}</h3>
            <ul className="space-y-1.5">
              {res.paths.slice(0, 10).map((p) => (
                <li key={p.id} className="flex flex-wrap items-center gap-2 rounded-md bg-raised/60 p-2 text-sm">
                  <Id>{p.id}</Id>
                  <span className="tnum font-mono text-xs" dir="ltr">{num(p.min)} – {num(p.max)} <span className="text-faint">({t('sens.baseline')} {num(p.baseline)})</span></span>
                  {p.severity_can_change && <span className="text-xs text-high-fg">{t('sens.sevChange')}</span>}
                  <span className={`ms-auto rounded border px-1.5 py-0.5 text-xs ${p.indicator === 'low' ? 'border-low/45 text-low-fg' : p.indicator === 'medium' ? 'border-med/45 text-med-fg' : 'border-crit/45 text-crit-fg'}`}>{t(`ind.${p.indicator}`)}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Panel>
  )
}

function Kpi({ label, value, sub }: { label: string; value: string; sub: string }) {
  return <div className="rounded-lg border border-hairline bg-raised/40 p-3"><p className="text-xs text-faint">{label}</p><p className="tnum mt-1 text-xl font-semibold" dir="ltr">{value}</p><p className="text-xs text-mist">{sub}</p></div>
}
