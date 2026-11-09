import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { actionText } from './helpers'
import { useI18n } from './i18n'
import { Icon } from './icons'
import type { Environment, Plan, PlansResponse, SimAction } from './types'
import { Button, Empty, EvidenceTag, Id, ImpactBadge, Panel, Spinner } from './ui'

interface Props {
  env: Environment
  onSimulatePlan: (actions: SimAction[]) => void
}

const LETTERS = 'ABCDEFGHIJ'

/** Compare defensive plans on four objectives. Pareto status is relative to the generated plans; nothing here claims global optimality. */
export default function PlansTab({ env, onSimulatePlan }: Props) {
  const { t, lang, num } = useI18n()
  const [data, setData] = useState<PlansResponse | null>(null)
  const [err, setErr] = useState('')
  const [sel, setSel] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    setData(null)
    api.plans().then((d) => { if (live) { setData(d); setSel(d.suggested_plan_id ?? d.plans[1]?.id ?? d.plans[0]?.id ?? null) } })
      .catch((e) => live && setErr(e instanceof Error ? e.message : String(e)))
    return () => { live = false }
  }, [env])

  if (err) return <p role="alert" className="text-sm text-crit-fg">{err}</p>
  if (!data) return <Spinner label={t('plans.loading')} />
  const plans = data.plans
  const plan = plans.find((p) => p.id === sel) ?? plans[0]
  const suggested = plans.find((p) => p.id === data.suggested_plan_id)

  return (
    <div className="space-y-4" data-testid="plans">
      <p className="text-sm text-mist">{t('plans.intro')}</p>
      <p className="flex gap-2 rounded-lg border border-hairline-2 bg-raised/50 p-3 text-xs text-mist"><Icon name="info" size={16} className="mt-px text-teal" />{t('plans.noOptimality')}</p>

      <Panel title={t('plans.suggested')} hint={t('plans.suggested.rule')}>
        {suggested ? (
          <div className="flex flex-wrap items-center gap-3" data-testid="plan-suggested">
            <b className="text-sm">{t(`plan.${suggested.strategy}`)}</b>
            <span className="text-sm text-mist">{suggested.summary[lang]}</span>
            <Button variant="quiet" onClick={() => setSel(suggested.id)}>{t('plans.show')}</Button>
          </div>
        ) : (
          <Empty icon="shield">{t('plans.noneSuggested')}</Empty>
        )}
        <p className="mt-3 text-xs text-faint">{t('plans.review')}</p>
      </Panel>

      <ParetoChart plans={plans} sel={plan.id} onSel={setSel} />

      <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" aria-label={t('plans.title')}>
        {plans.map((p, i) => (
          <li key={p.id}>
            <button onClick={() => setSel(p.id)} aria-pressed={p.id === plan.id} data-testid={`plan-card-${p.strategy}`}
              className={`flex h-full w-full flex-col gap-2 rounded-lg border p-3 text-start transition-colors ${p.id === plan.id ? 'border-teal/60 bg-teal/10' : 'border-hairline bg-surface hover:bg-raised'}`}>
              <span className="flex items-center gap-2">
                <span className="grid size-6 place-items-center rounded border border-hairline-2 font-mono text-xs text-mist" aria-hidden>{LETTERS[i]}</span>
                <b className="text-sm">{t(`plan.${p.strategy}`)}</b>
                <ParetoBadge plan={p} />
              </span>
              <span className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-mist">
                <span>{t('plans.paths')}: <b className="tnum text-cloud">{p.metrics.paths_before} → {p.metrics.paths_after}</b></span>
                <span>{t('plans.posture')}: <b className="tnum text-cloud">{num(p.metrics.posture_after)}</b></span>
                <span>{t('plans.disruption')}: <b className="tnum text-cloud">{num(p.disruption_cost)}</b></span>
                <span>{t('plans.effort')}: <b className="tnum text-cloud">{p.effort}</b></span>
              </span>
              <span className="flex flex-wrap items-center gap-1.5"><ImpactBadge level={p.operational.level} />
                <span className="text-xs text-faint">{p.operational.fully_reversible ? t('sim.reversible') : t('sim.irreversible')}</span></span>
            </button>
          </li>
        ))}
      </ul>

      <PlanDetail env={env} plan={plan} onSimulatePlan={onSimulatePlan} />
    </div>
  )
}

function ParetoBadge({ plan }: { plan: Plan }) {
  const { t } = useI18n()
  return plan.pareto.optimal
    ? <span className="ms-auto rounded border border-teal/50 bg-teal/10 px-1.5 py-0.5 text-[11px] font-medium text-teal">{t('plans.pareto')}</span>
    : <span className="ms-auto rounded border border-hairline-2 px-1.5 py-0.5 text-[11px] text-faint">{t('plans.dominated')}</span>
}

/** Disruption (x) against residual posture (y): lower-left is better. Filled = not dominated by another generated plan. */
function ParetoChart({ plans, sel, onSel }: { plans: Plan[]; sel: string; onSel: (id: string) => void }) {
  const { t } = useI18n()
  const W = 560, H = 250, L = 46, B = 36, T = 14, R = 16
  const maxX = Math.max(1, ...plans.map((p) => p.disruption_cost)) * 1.1
  const maxY = Math.max(1, ...plans.map((p) => p.metrics.posture_after)) * 1.1
  const px = (v: number) => L + (v / maxX) * (W - L - R)
  const py = (v: number) => H - B - (v / maxY) * (H - B - T)
  return (
    <Panel title={t('plans.chart')} hint={t('plans.chart.hint')}>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={t('plans.chart.aria')} style={{ direction: 'ltr' }}>
        <line x1={L} y1={H - B} x2={W - R} y2={H - B} stroke="#2c3f62" /><line x1={L} y1={T} x2={L} y2={H - B} stroke="#2c3f62" />
        <text x={(L + W - R) / 2} y={H - 6} textAnchor="middle" fill="#a3b4d0" fontSize="12">{t('plans.disruption')}</text>
        <text x={12} y={(T + H - B) / 2} textAnchor="middle" fill="#a3b4d0" fontSize="12" transform={`rotate(-90 12 ${(T + H - B) / 2})`}>{t('plans.posture')}</text>
        {[0, 0.5, 1].map((f) => <text key={f} x={L - 6} y={py(f * maxY / 1.1) + 4} textAnchor="end" fill="#8497b8" fontSize="11">{Math.round(f * maxY / 1.1)}</text>)}
        {[0, 0.5, 1].map((f) => <text key={f} x={px(f * maxX / 1.1)} y={H - B + 14} textAnchor="middle" fill="#8497b8" fontSize="11">{(f * maxX / 1.1).toFixed(1)}</text>)}
        {plans.map((p, i) => (
          <g key={p.id} onClick={() => onSel(p.id)} style={{ cursor: 'pointer' }}>
            <circle cx={px(p.disruption_cost)} cy={py(p.metrics.posture_after)} r={p.id === sel ? 9 : 7} fill={p.pareto.optimal ? '#34d1bf' : '#060a14'} stroke={p.pareto.optimal ? '#34d1bf' : '#8497b8'} strokeWidth={p.id === sel ? 3 : 2} />
            <text x={px(p.disruption_cost)} y={py(p.metrics.posture_after) - 12} textAnchor="middle" fill="#e8eef9" fontSize="12" fontWeight="600">{LETTERS[i]}</text>
          </g>
        ))}
      </svg>
      <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-mist">
        <span className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-teal" aria-hidden />{t('plans.pareto')}</span>
        <span className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-full border-2 border-faint" aria-hidden />{t('plans.dominated')}</span>
        {plans.map((p, i) => <span key={p.id}><b className="font-mono text-cloud">{LETTERS[i]}</b> {t(`plan.${p.strategy}`)}</span>)}
      </p>
    </Panel>
  )
}

function PlanDetail({ env, plan, onSimulatePlan }: { env: Environment; plan: Plan; onSimulatePlan: (a: SimAction[]) => void }) {
  const { t, lang, assetName, num, arrow } = useI18n()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const m = plan.metrics
  const names = useMemo(() => new Map(env.assets.map((a) => [a.id, assetName(a)])), [env, assetName])

  const download = async () => {
    setBusy(true)
    setErr('')
    try {
      const r = await api.planReport(plan.id, lang)
      const url = URL.createObjectURL(new Blob([r.markdown], { type: 'text/markdown;charset=utf-8' }))
      const a = document.createElement('a')
      a.href = url
      a.download = `athar-decision-record-${plan.id}-${lang}.md`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel title={t(`plan.${plan.strategy}`)} hint={t(`plan.${plan.strategy}.desc`)} id="plan-detail"
      action={plan.actions.length > 0 ? <ParetoBadge plan={plan} /> : undefined}>
      <div className="space-y-5 text-sm">
        <p className="text-mist">{plan.summary[lang]}</p>
        {plan.pareto.dominated_by.length > 0 && <p className="text-xs text-faint">{t('plans.dominatedBy', { n: plan.pareto.dominated_by.length })}</p>}

        <div>
          <h3 className="mb-1.5 text-xs font-semibold text-faint">{t('plans.actions')}</h3>
          {plan.actions.length === 0 ? <p className="text-mist">{t('plans.noActions')}</p> : (
            <ol className="list-decimal space-y-1 ps-5">{plan.actions.map((a, i) => <li key={i}>{actionText(a, env, t, (x) => assetName(x))}</li>)}</ol>
          )}
        </div>

        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label={t('plans.paths')} value={`${m.paths_before} → ${m.paths_after}`} />
          <Stat label={t('plans.posture')} value={`${num(m.posture_before)} → ${num(m.posture_after)}`} />
          <Stat label={t('plans.maxResidual')} value={num(m.max_residual_score)} />
          <Stat label={t('plans.residualValidated')} value={String(m.residual_validated)} />
          <Stat label={t('plans.disruption')} value={num(plan.disruption_cost)} />
          <Stat label={t('plans.effort')} value={String(plan.effort)} />
          <Stat label={t('plans.lostAccess')} value={String(plan.operational.lost_access)} />
          <Stat label={t('plans.affectedAssets')} value={String(plan.operational.affected_assets.length)} />
        </dl>

        <div>
          <h3 className="mb-1.5 text-xs font-semibold text-faint">{t('plans.business')}</h3>
          {env.services && env.services.length > 0 ? (
            plan.business.services.length === 0 ? <p className="text-mist">{t('plans.business.none')}</p> : (
              <ul className="space-y-1.5" data-testid="plan-services">
                {plan.business.services.map((s) => (
                  <li key={s.service_id} className="rounded-md bg-raised/60 p-2">
                    <b>{lang === 'ar' ? s.name_ar : s.name}</b> <span className="text-faint">· {t('svc.criticality')} {s.criticality}/5</span>
                    <div className="mt-0.5 text-xs text-mist">{t(`effect.${s.effect}`)} · {t(`recovery.${s.recovery}`)}{s.recovery_hours ? ` (${s.recovery_hours} h)` : ''} · RTO {s.rto_hours} h: <b>{t(`rto.${s.rto_status}`)}</b></div>
                  </li>
                ))}
                <li className="text-xs text-faint">{t('plans.bii', { n: num(plan.business.business_impact_index) })}</li>
              </ul>
            )
          ) : <p className="text-mist">{t('plans.business.undeclared')}</p>}
        </div>

        <div>
          <h3 className="mb-1.5 text-xs font-semibold text-faint">{t('plans.residual')}</h3>
          {plan.residual_top.length === 0 ? <p className="text-mist">{t('plans.residual.none')}</p> : (
            <ul className="space-y-1.5">
              {plan.residual_top.map((p) => (
                <li key={p.path_id} className="flex flex-wrap items-center gap-2 rounded-md bg-raised/60 p-2">
                  <span className="min-w-0 flex-1">{p.nodes.map((n) => names.get(n) ?? n).join(` ${arrow} `)}</span>
                  <EvidenceTag level={p.classification} /><span className="tnum font-mono text-xs text-mist">{num(p.score)}</span>
                  <Id>{p.path_id}</Id>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <h3 className="mb-1.5 text-xs font-semibold text-faint">{t('plans.approvals')}</h3>
          {plan.approvals.length === 0 ? <p className="text-mist">—</p> : (
            <ul className="flex flex-wrap gap-2">{plan.approvals.map((a) => <li key={a.role} className="rounded border border-hairline-2 px-2 py-1 text-xs"><b>{t(`role.${a.role}`)}</b><span className="text-faint"> · {a.why.map((w) => t(`why.${w}`)).join('; ')}</span></li>)}</ul>
          )}
        </div>

        <div className="flex flex-wrap gap-2 border-t border-hairline pt-4">
          <Button variant="primary" icon="sliders" disabled={plan.actions.length === 0} onClick={() => onSimulatePlan(plan.actions)} data-testid="plan-simulate">{t('plans.simulate')}</Button>
          <Button icon="download" disabled={busy} onClick={() => void download()} data-testid="plan-report">{t('plans.report')}</Button>
        </div>
        {err && <p role="alert" className="text-crit-fg">{err}</p>}
        <p className="flex items-start gap-2 text-xs text-faint"><Icon name="lock" size={14} className="mt-px" />{t('rec.approval.help')}</p>
      </div>
    </Panel>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs text-faint">{label}</dt><dd className="tnum mt-0.5 font-medium" dir="ltr">{value}</dd></div>
}
