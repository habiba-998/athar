import { useState } from 'react'
import GraphView, { type Selection } from './GraphView'
import { actionKey, actionText, findAsset, findRel, pathEvidence, pathsById, relText, routeNames } from './helpers'
import { useI18n } from './i18n'
import { Icon, type IconName } from './icons'
import RouteTrace from './RouteTrace'
import type { AttackPath, Environment, SimAction, SimRecord, SimResult } from './types'
import { Button, Empty, EvidenceTag, Field, ImpactBadge, Panel, SEV, SEVERITIES, SeverityBadge, Spinner, StackedBar, controlCls } from './ui'

const KINDS = ['remove_relationship', 'disable_relationship', 'reduce_privilege', 'apply_mfa', 'apply_segmentation'] as const
type Kind = (typeof KINDS)[number]
const KIND_ICON: Record<Kind, IconName> = { remove_relationship: 'trash', disable_relationship: 'x', reduce_privilege: 'sliders', apply_mfa: 'lock', apply_segmentation: 'shield' }

interface Props {
  env: Environment
  queue: SimAction[]
  setQueue: (q: SimAction[]) => void
  sim: SimResult | null
  history: SimRecord[]
  busy: boolean
  error: string
  onRun: () => void
  onReset: () => void
  onUndo: () => void
  onView: (id: number) => void
  selection: Selection
  setSelection: (s: Selection) => void
}

export default function SimTab({ env, queue, setQueue, sim, history, busy, error, onRun, onReset, onUndo, onView, selection, setSelection }: Props) {
  const { t, assetName, arrow } = useI18n()
  const [kind, setKind] = useState<Kind>('remove_relationship')
  const [target, setTarget] = useState('')

  const byRel = kind === 'remove_relationship' || kind === 'disable_relationship' || kind === 'reduce_privilege'
  const options = byRel
    ? env.relationships.filter((r) => r.type !== 'protects').map((r) => ({ id: r.id, label: relText(env, r, t, assetName) }))
    : env.assets.filter((a) => a.type !== 'control').map((a) => ({ id: a.id, label: assetName(a) }))
  const chosen = target && options.some((o) => o.id === target) ? target : (options[0]?.id ?? '')

  const add = () => {
    if (!chosen) return
    const a: SimAction =
      kind === 'remove_relationship' ? { kind, relationship_id: chosen }
      : kind === 'disable_relationship' ? { kind, relationship_id: chosen }
      : kind === 'reduce_privilege' ? { kind, relationship_id: chosen, to: 'read' }
      : { kind, asset_id: chosen }
    if (!queue.some((q) => actionKey(q) === actionKey(a))) setQueue([...queue, a])
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
      <div className="space-y-4">
        <Panel title={t('sim.title')} hint={t('sim.intro')}>
          <div className="space-y-4">
            <Field label={t('sim.action')} hint={t(`action.help.${kind}`)}>
              {({ id, describedBy }) => (
                <select id={id} aria-describedby={describedBy} value={kind} onChange={(e) => setKind(e.target.value as Kind)} className={controlCls}>
                  {KINDS.map((k) => <option key={k} value={k}>{t(`action.${k}`)}</option>)}
                </select>
              )}
            </Field>
            <Field label={t('sim.target')}>
              {({ id }) => (
                <select id={id} value={chosen} onChange={(e) => setTarget(e.target.value)} className={controlCls}>
                  {options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                </select>
              )}
            </Field>
            <Button icon="plus" onClick={add} className="w-full">{t('sim.add')}</Button>
          </div>
        </Panel>

        <Panel title={t('sim.queue')} hint={t('sim.approval')}>
          {queue.length === 0 ? (
            <Empty icon="sliders">{t('sim.queue.empty')}</Empty>
          ) : (
            <ul className="space-y-2" data-testid="sim-queue">
              {queue.map((a) => (
                <li key={actionKey(a)} className="flex items-start gap-3 rounded-md border border-hairline bg-raised/50 p-2.5 text-sm">
                  <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-md border border-hairline-2 bg-raised text-mist"><Icon name={KIND_ICON[a.kind]} size={15} /></span>
                  <span className="min-w-0 flex-1 pt-0.5">{actionText(a, env, t, assetName)}</span>
                  <Button variant="quiet" aria-label={`${t('sim.remove')}: ${actionText(a, env, t, assetName)}`} onClick={() => setQueue(queue.filter((q) => actionKey(q) !== actionKey(a)))}>
                    {t('sim.remove')}
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="primary" icon="sliders" onClick={onRun} disabled={busy || queue.length === 0} className="flex-1" data-testid="sim-run">{busy ? t('sim.running') : t('sim.run')}</Button>
            <Button icon="undo" onClick={onUndo} disabled={busy || queue.length === 0}>{t('sim.undo')}</Button>
            <Button variant="quiet" onClick={onReset} disabled={busy || (queue.length === 0 && !sim)}>{t('sim.reset')}</Button>
          </div>
        </Panel>

        <Panel title={t('sim.history')} hint={t('sim.history.hint')}>
          {history.length === 0 ? (
            <Empty icon="list">{t('sim.history.empty')}</Empty>
          ) : (
            <ul className="space-y-2 text-sm" data-testid="sim-history">
              {history.slice(0, 8).map((h) => (
                <li key={h.id} className="rounded-md border border-hairline bg-raised/50 p-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <bdi dir="ltr" className="font-mono text-xs text-faint">#{h.id} · <time dateTime={h.time}>{h.time.slice(0, 19).replace('T', ' ')}</time></bdi>
                    <Button variant="quiet" aria-label={`${t('sim.view')} #${h.id}`} onClick={() => onView(h.id)}>{t('sim.view')}</Button>
                  </div>
                  <p className="mt-1 text-xs text-mist">
                    {h.actions.map((a) => actionText(a, env, t, assetName)).join('; ')}
                    <span className="tnum text-faint"> · {h.paths_before} {arrow} {h.paths_after}</span>
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="min-w-0 space-y-4">
        {busy && <Spinner label={t('sim.running')} />}
        {error && <p role="alert" className="flex gap-2 rounded-lg border border-crit/50 bg-crit/10 p-3 text-sm text-crit-fg"><Icon name="alert" size={18} />{error}</p>}
        {!sim && !busy && !error && (
          <Panel><Empty icon="sliders">{t('dash.comparison.empty')}</Empty></Panel>
        )}
        {sim && (
          <>
            {sim.record_id != null && sim.current_environment === false ? (
              <p role="status" className="flex gap-2 rounded-lg border border-med/50 bg-med/10 p-3 text-sm text-med-fg">
                <Icon name="alert" size={18} />
                <span>{t('sim.viewing', { id: sim.record_id })} · {t('sim.recorded')} {sim.recorded_at?.slice(0, 19).replace('T', ' ')}. {t('sim.stale')}</span>
              </p>
            ) : (
              <p role="status" className="flex gap-2 rounded-lg border border-teal/40 bg-teal/10 p-3 text-sm text-teal">
                <Icon name="check" size={18} /> {t('sim.success')} {sim.record_id != null && <bdi dir="ltr">#{sim.record_id}</bdi>} {sim.ephemeral && <span className="text-mist">· {t("sim.ephemeral")}</span>}
              </p>
            )}
            <Comparison sim={sim} />
            <SimDetails env={env} sim={sim} />
            <Panel title={t('dash.graph')}>
              <GraphView env={env} path={null} sim={sim} selection={selection} onSelect={setSelection} height={420} />
            </Panel>
          </>
        )}
      </div>
    </div>
  )
}

/** Before / after, with real counts and scores. Percentages are secondary and say exactly what they measure. */
export function Comparison({ sim }: { sim: SimResult }) {
  const { t, num, arrow } = useI18n()
  const rows: { label: string; b: number; a: number }[] = [
    { label: t('kpi.paths'), b: sim.before.attack_paths, a: sim.after.attack_paths },
    { label: t('kpi.validated'), b: sim.before.validated_paths, a: sim.after.validated_paths },
    { label: t('kpi.posture'), b: sim.before.posture_score, a: sim.after.posture_score },
    { label: 'Σ ' + t('score'), b: sim.before.total_path_score, a: sim.after.total_path_score },
  ]
  const delta = (b: number, a: number) => {
    const d = Math.round((a - b) * 10) / 10
    return d === 0 ? '0' : d > 0 ? `+${num(d)}` : `−${num(Math.abs(d))}`
  }
  return (
    <Panel title={t('dash.comparison')}>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3" data-testid="before-after">
        <div className="rounded-lg border border-hairline bg-raised/50 p-4">
          <p className="text-xs font-medium text-faint">{t('sim.before')}</p>
          <p className="tnum mt-1 text-4xl font-semibold leading-none">{num(sim.before.attack_paths)}</p>
          <p className="mt-1 text-xs text-mist">{t('kpi.paths')}</p>
          <p className="tnum mt-3 text-sm text-mist">{t('kpi.posture')} <b className="text-cloud">{num(sim.before.posture_score)}</b></p>
        </div>
        <span className="text-2xl text-faint" aria-hidden>{arrow}</span>
        <div className="rounded-lg border border-teal/40 bg-teal/5 p-4">
          <p className="text-xs font-medium text-faint">{t('sim.after')}</p>
          <p className="tnum mt-1 text-4xl font-semibold leading-none text-teal">{num(sim.after.attack_paths)}</p>
          <p className="mt-1 text-xs text-mist">{t('kpi.paths')}</p>
          <p className="tnum mt-3 text-sm text-mist">{t('kpi.posture')} <b className="text-cloud">{num(sim.after.posture_score)}</b></p>
        </div>
      </div>

      <div className="mt-5 space-y-2.5">
        <h3 className="text-xs font-semibold text-faint">{t('sim.severity.title')}</h3>
        {(['before', 'after'] as const).map((k) => (
          <div key={k} className="grid grid-cols-[3.5rem_1fr] items-center gap-3">
            <span className="text-xs text-mist">{t(`sim.${k}`)}</span>
            <StackedBar label={SEVERITIES.map((s) => `${t('sev.' + s)}: ${sim[k].severity_distribution[s]}`).join(', ')}
              segments={SEVERITIES.map((s) => ({ value: sim[k].severity_distribution[s], className: SEV[s].bar }))} />
          </div>
        ))}
        <ul className="flex flex-wrap gap-x-4 gap-y-1 ps-[3.5rem] text-xs text-mist">
          {SEVERITIES.map((s) => <li key={s} className="flex items-center gap-1.5"><span className={`size-2 rounded-sm ${SEV[s].fill}`} aria-hidden />{t('sev.' + s)} <span className="tnum text-faint">{sim.before.severity_distribution[s]} {arrow} {sim.after.severity_distribution[s]}</span></li>)}
        </ul>
      </div>

      <table className="mt-5 w-full text-sm" data-testid="comparison">
        <thead>
          <tr className="text-xs text-faint">
            <th scope="col" className="py-1.5 text-start font-medium"><span className="sr-only">{t('score')}</span></th>
            <th scope="col" className="py-1.5 text-start font-medium">{t('sim.before')}</th>
            <th scope="col" className="py-1.5 text-start font-medium">{t('sim.after')}</th>
            <th scope="col" className="py-1.5 text-start font-medium">{t('sim.delta')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-t border-hairline">
              <th scope="row" className="py-2 pe-3 text-start font-normal text-mist">{r.label}</th>
              <td className="tnum font-mono">{num(r.b)}</td>
              <td className={`tnum font-mono ${r.a < r.b ? 'text-teal' : ''}`}>{num(r.a)}</td>
              <td className={`tnum font-mono text-xs ${r.a < r.b ? 'text-teal' : 'text-faint'}`} dir="ltr">{delta(r.b, r.a)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 space-y-1 text-xs text-faint">
        <p>{t('sim.reduction')}: <b className="text-mist">{num(sim.risk_reduction_pct)}%</b> · {t('sim.scoreReduction')}: <b className="text-mist">{num(sim.path_score_reduction_pct)}%</b></p>
        <p>{t('sim.note.percent')}</p>
      </div>
    </Panel>
  )
}

function SimDetails({ env, sim }: { env: Environment; sim: SimResult }) {
  const { t, assetName, lang, num, arrow } = useI18n()
  const [all, setAll] = useState(false)
  const imp = sim.operational_impact
  const before = pathsById(sim.before_paths)
  const after = pathsById(sim.after_paths)
  const blocked = new Set(imp.affected_relationships.filter((i) => ['remove_relationship', 'disable_relationship', 'apply_segmentation'].includes(i.action)).map((i) => i.relationship_id))
  const cutIndex = (p: AttackPath) => p.steps.findIndex((s) => blocked.has(s.relationship_id))
  const eliminated = sim.paths_eliminated.map((id) => before.get(id)).filter((p): p is AttackPath => !!p)
  const shownElim = all ? eliminated : eliminated.slice(0, 4)

  return (
    <>
      <div className="grid gap-4 md:grid-cols-5">
        <Panel className="md:col-span-2" title={t('sim.eliminated')}>
          <p className="tnum text-5xl font-semibold leading-none text-teal" data-testid="eliminated-count">{sim.paths_eliminated.length}</p>
          <p className="mt-3 text-sm text-mist">{t('sim.mitigated')}: <b className="tnum text-cloud">{sim.paths_mitigated.length}</b></p>
          <p className="mt-1 text-sm text-mist">{t('sim.paths.remaining')}: <b className="tnum text-cloud">{sim.paths_remaining.length}</b></p>
        </Panel>
        <Panel className="md:col-span-3" title={t('sim.impact')}>
          <div className="flex flex-wrap items-center gap-2">
            <span data-testid="impact-level"><ImpactBadge level={imp.level} /></span>
            <span className={`inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-xs font-medium ${imp.fully_reversible ? 'border-teal/45 bg-teal/10 text-teal' : 'border-hairline-2 bg-raised text-mist'}`}>
              <Icon name={imp.fully_reversible ? 'undo' : 'lock'} size={13} />{imp.fully_reversible ? t('sim.reversible') : t('sim.irreversible')}
            </span>
          </div>
          <p className="mt-2 text-sm text-mist">{imp.fully_reversible ? t('sim.fullyReversible') : t('sim.irreversible.help')}</p>
          <h3 className="mt-4 text-xs font-semibold text-faint">{t('sim.affectedAssets')}</h3>
          <ul className="mt-1.5 flex flex-wrap gap-1.5" data-testid="affected-assets">
            {imp.affected_assets.map((id) => <li key={id} className="rounded-md border border-hairline-2 bg-raised px-2 py-0.5 text-xs">{assetName(findAsset(env, id))}</li>)}
          </ul>
        </Panel>
      </div>

      <Panel title={t('sim.sideEffects')}>
        {imp.lost_access.length === 0 ? (
          <p className="flex gap-2 text-sm text-mist" data-testid="lost-access"><Icon name="check" size={18} className="text-low-fg" />{t('sim.noSideEffects')}</p>
        ) : (
          <ul className="space-y-1.5 text-sm" data-testid="lost-access">
            {imp.lost_access.map((l) => (
              <li key={l.identity + l.asset} className="flex gap-2 rounded-md border border-high/35 bg-high/10 p-2 text-high-fg"><Icon name="alert" size={16} className="mt-0.5" />
                <span>{assetName(findAsset(env, l.identity))} {arrow} {assetName(findAsset(env, l.asset))}</span></li>
            ))}
          </ul>
        )}
        <h3 className="mb-2 mt-5 text-xs font-semibold text-faint">{t('sim.impact.affected')}</h3>
        <ul className="space-y-2 text-sm">
          {imp.affected_relationships.map((i, n) => {
            const r = findRel(env, i.relationship_id)
            return (
              <li key={i.relationship_id + n} className="rounded-md border border-hairline bg-raised/50 p-2.5">
                <div>{r ? relText(env, r, t, assetName) : i.relationship_id}</div>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-mist">
                  <span>{t(`action.${i.action}`)}</span><ImpactBadge level={i.level} />
                  <span>{i.reversible ? t('sim.reversible') : t('sim.irreversible')}</span>
                </div>
                <div className="mt-1 text-xs text-faint">{t('detail.legit')}: {(lang === 'ar' ? i.legitimate_use_ar : i.legitimate_use) ?? t('detail.nolegit')}</div>
              </li>
            )
          })}
        </ul>
      </Panel>

      {eliminated.length > 0 && (
        <Panel title={t('sim.paths.eliminated')} hint={t('sim.paths.eliminated.hint', { n: eliminated.length })}>
          <ul className="space-y-4" data-testid="eliminated-paths">
            {shownElim.map((p) => (
              <li key={p.id} className="rounded-md border border-hairline bg-raised/40 p-3">
                <div className="mb-3 flex flex-wrap items-center gap-1.5"><SeverityBadge severity={p.severity} /><EvidenceTag level={p.classification} /><span className="tnum ms-auto font-mono text-xs text-faint">{num(p.score)}</span></div>
                <RouteTrace names={routeNames(env, p.nodes, assetName)} evidence={pathEvidence(p)} severity={p.severity} cutAt={cutIndex(p)} />
              </li>
            ))}
          </ul>
          {eliminated.length > 4 && <Button variant="quiet" className="mt-3" onClick={() => setAll((v) => !v)}>{all ? t('sim.showFewer') : t('sim.showAll', { n: eliminated.length })}</Button>}
        </Panel>
      )}

      <Panel title={t('sim.residual')} hint={t('sim.residual.hint')}>
        {sim.residual_risks.length === 0 ? (
          <Empty icon="check">{t('sim.residual.none')}</Empty>
        ) : (
          <ul className="space-y-2 text-sm" data-testid="residual">
            {sim.residual_risks.map((r) => {
              const p = after.get(r.path_id)
              return (
                <li key={r.path_id} className="flex flex-wrap items-center gap-2 rounded-md border border-hairline bg-raised/40 p-2.5">
                  <SeverityBadge severity={r.severity} />
                  <span className="min-w-0 flex-1 text-mist">{p ? routeNames(env, p.nodes, assetName).join(` ${arrow} `) : r.path_id}</span>
                  {r.score < r.score_before && <span className="rounded border border-high/40 px-1.5 text-xs text-high-fg">{t('sim.mitigatedTag')}</span>}
                  <span className="tnum font-mono text-xs text-mist">{num(r.score_before)} {arrow} {num(r.score)}</span>
                </li>
              )
            })}
          </ul>
        )}
      </Panel>
    </>
  )
}
