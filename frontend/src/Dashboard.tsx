import GraphView, { type Selection } from './GraphView'
import { assetsAtRisk, BANDS, findAsset, findRel, pathEvidence, routeNames } from './helpers'
import { useI18n } from './i18n'
import { Icon, TYPE_ICON } from './icons'
import RecsList from './RecsTab'
import RouteTrace from './RouteTrace'
import type { Activity, Analysis, Environment, Finding, Recommendation, Severity, SimAction, SimResult } from './types'
import { Button, Empty, EvidenceTag, Panel, Pips, SEV, SEVERITIES, SeverityBadge, StackedBar } from './ui'

interface Props {
  env: Environment
  analysis: Analysis
  recs: Recommendation[]
  activity: Activity[]
  sim: SimResult | null
  selection: Selection
  setSelection: (s: Selection) => void
  goto: (tab: string) => void
  openPath: (id: string) => void
  onSimulate: (a: SimAction) => void
  onActivity: () => void
}

export default function Dashboard({ env, analysis, recs, activity, sim, selection, setSelection, goto, openPath, onSimulate, onActivity }: Props) {
  const { t, assetName, num } = useI18n()
  const s = analysis.summary
  const top = analysis.paths[0] ?? null
  const risked = assetsAtRisk(analysis, env)
  const dist = s.severity_distribution
  const actNow = analysis.findings.filter((f) => f.severity === 'critical' || f.severity === 'high')
  const review = analysis.findings.filter((f) => f.severity === 'medium' || f.severity === 'low')
  // never print a raw message key: unknown event kinds fall back to a generic label
  const activityLabel = (kind: string) => (t(`act.${kind}`) === `act.${kind}` ? t('act.other') : t(`act.${kind}`))

  const stats: { label: string; value: string; sub: string; help?: string }[] = [
    { label: t('kpi.assets'), value: num(s.total_assets), sub: t('kpi.sub.critical', { n: s.critical_assets }) },
    { label: t('kpi.paths'), value: num(s.attack_paths), sub: t('kpi.sub.validated', { n: s.validated_paths }) },
    { label: t('kpi.atRisk'), value: num(risked.length), sub: t('kpi.atRisk.sub') },
    { label: t('kpi.maxScore'), value: num(s.max_path_score), sub: top ? t(`sev.${top.severity}`) : '—' },
  ]

  return (
    <div className="space-y-4">
      {s.paths_truncated && (
        <p role="alert" data-testid="truncated-warning" className="flex gap-2 rounded-lg border border-med/50 bg-med/10 p-3 text-sm text-med-fg">
          <Icon name="alert" size={18} /> {t('warn.truncated')}
        </p>
      )}

      {(s.compromised_sensitive_assets?.length ?? 0) > 0 && (
        <p role="status" data-testid="owned-warning" className="flex gap-2 rounded-lg border border-high/50 bg-high/10 p-3 text-sm text-high-fg">
          <Icon name="alert" size={18} />
          <span>{t('warn.owned', { assets: s.compromised_sensitive_assets!.map((id) => assetName(findAsset(env, id)) || id).join(', ') })}</span>
        </p>
      )}

      {/* Thesis: lead with the single most dangerous path, drawn as a trace. */}
      <div className="grid gap-4 lg:grid-cols-12">
        <Panel className="lg:col-span-8" title={t('dash.hero.title')} hint={t('dash.hero.hint')}
          action={top && <div className="flex flex-wrap items-center justify-end gap-1.5"><SeverityBadge severity={top.severity} /><EvidenceTag level={top.classification} /></div>}>
          {top ? (
            <div data-testid="hero-path" className="space-y-5">
              <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                <p className="text-xl font-semibold">{assetName(findAsset(env, top.target))}</p>
                <p className="text-sm text-mist"><bdi dir="ltr"><span className={`tnum text-2xl font-semibold ${SEV[top.severity].text}`}>{num(top.score)}</span><span className="text-faint"> / 100</span></bdi> · {top.steps.length} {t('hops')}</p>
              </div>
              <div className="pb-1 pt-1"><RouteTrace names={routeNames(env, top.nodes, assetName)} evidence={pathEvidence(top)} severity={top.severity} /></div>
              <p className="text-sm text-mist">{t('dash.hero.sentence', { source: assetName(findAsset(env, top.source)), target: assetName(findAsset(env, top.target)), hops: top.steps.length })}</p>
              <div className="flex flex-wrap gap-2">
                <Button variant="primary" icon="graph" onClick={() => openPath(top.id)}>{t('dash.hero.open')}</Button>
                <Button icon="bulb" onClick={() => goto('recommendations')}>{t('dash.hero.fixes')}</Button>
              </div>
            </div>
          ) : (
            <Empty icon="shield">{t('dash.hero.none')}</Empty>
          )}
        </Panel>

        <Panel className="lg:col-span-4" title={t('kpi.posture')} hint={t('kpi.posture.hint')}>
          <p className="tnum text-4xl font-semibold" data-testid="posture"><bdi dir="ltr">{num(s.posture_score)}<span className="text-base font-normal text-faint"> / 100</span></bdi></p>
          <div className="relative mt-4 h-2 rounded-sm bg-hairline" role="img" aria-label={`${t('kpi.posture')}: ${num(s.posture_score)} / 100`}>
            <div className="grow absolute inset-y-0 start-0 rounded-sm bg-teal" style={{ width: `${Math.min(100, s.posture_score)}%` }} />
            {BANDS.map((b) => <span key={b.min} className="absolute inset-y-[-3px] w-px bg-cloud/40" style={{ insetInlineStart: `${b.min}%` }} />)}
          </div>
          <div className="relative mt-1.5 h-4 text-[11px] text-faint" aria-hidden>
            {BANDS.map((b) => <span key={b.min} className="absolute -translate-x-1/2 rtl:translate-x-1/2" style={{ insetInlineStart: `${b.min}%` }}>{b.min}</span>)}
          </div>
          <p className="mt-3 text-xs leading-relaxed text-faint">{t('kpi.posture.help')}</p>
        </Panel>
      </div>

      <div data-testid="kpis" className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-hairline bg-hairline lg:grid-cols-4">
        {stats.map((x) => (
          <section key={x.label} className="bg-surface px-4 py-3.5">
            <h2 className="text-xs font-medium text-faint">{x.label}</h2>
            <p className="tnum mt-1 text-3xl font-semibold leading-none">{x.value}</p>
            <p className="mt-1.5 text-xs text-mist">{x.sub}</p>
          </section>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-12 lg:items-start">
        <Panel className="lg:col-span-5" title={t('dash.distribution')} hint={t('dash.distribution.hint')}>
          <StackedBar label={SEVERITIES.map((k) => `${t('sev.' + k)}: ${dist[k]}`).join(', ')} className="h-3"
            segments={SEVERITIES.map((k) => ({ value: dist[k], className: SEV[k].bar }))} />
          <ul className="mt-5 space-y-3.5" data-testid="distribution">
            {SEVERITIES.map((k: Severity) => (
              <li key={k} className="grid grid-cols-[6.5rem_1fr_2rem] items-center gap-3 text-sm">
                <span><SeverityBadge severity={k} /></span>
                <span className="h-1.5 rounded-sm bg-hairline" aria-hidden><span className={`grow block h-full rounded-sm ${SEV[k].bar}`} style={{ width: `${(100 * dist[k]) / Math.max(1, ...SEVERITIES.map((x) => dist[x]))}%` }} /></span>
                <span className="tnum text-end font-medium">{dist[k]}</span>
              </li>
            ))}
          </ul>
          <p className="mt-5 text-xs text-faint">{t('dash.distribution.note')}</p>
        </Panel>

        <Panel className="lg:col-span-7" title={t('dash.assetsAtRisk')} hint={t('dash.assetsAtRisk.hint')} flush>
          {risked.length === 0 ? (
            <div className="p-4"><Empty icon="shield">{t('dash.assetsAtRisk.none')}</Empty></div>
          ) : (
            <ul data-testid="assets-at-risk" className="divide-y divide-hairline">
              {risked.slice(0, 5).map((r) => (
                <li key={r.asset.id}>
                  <button onClick={() => openPath(r.worst.id)} className="flex w-full items-center gap-3 px-4 py-3 text-start hover:bg-raised max-sm:min-h-14">
                    <span className="grid size-9 shrink-0 place-items-center rounded-md border border-hairline-2 bg-raised text-mist"><Icon name={TYPE_ICON[r.asset.type] ?? 'server'} size={18} /></span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{assetName(r.asset)}</span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-faint">
                        <span>{t(`type.${r.asset.type}`)}</span><Pips n={r.asset.criticality} /><span>{t(`exp.${r.asset.exposure}`)}</span>
                      </span>
                    </span>
                    <span className="text-end">
                      <span className={`tnum block text-lg font-semibold leading-none ${SEV[r.worst.severity].text}`}>{num(r.worst.score)}</span>
                      <span className="text-xs text-faint">{t('dash.paths.n', { n: r.paths })}</span>
                    </span>
                    <Icon name="chevron" size={16} className="text-faint" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-12 lg:items-start">
        <Panel className="lg:col-span-7" title={t('dash.findings')} action={<Button variant="quiet" onClick={() => goto('graph')}>{t('dash.viewAll')}</Button>}>
          <div data-testid="findings" className="space-y-5">
            <FindingGroup title={t('dash.findings.act')} hint={t('dash.findings.act.hint')} list={actNow} limit={5} env={env} onOpen={(f) => (f.path_id ? openPath(f.path_id) : goto('environment'))} />
            <FindingGroup title={t('dash.findings.review')} hint={t('dash.findings.review.hint')} list={review} limit={4} env={env} onOpen={(f) => (f.path_id ? openPath(f.path_id) : goto('environment'))} />
          </div>
        </Panel>

        <Panel className="lg:col-span-5" title={t('dash.activity')} hint={t('dash.activity.hint')}>
          <ul className="relative space-y-3 border-s border-hairline-2 ps-4" data-testid="activity">
            {activity.slice(0, 6).map((a, i) => (
              <li key={a.time + a.kind + i} className="relative flex items-baseline justify-between gap-3 text-sm">
                <span className="absolute -start-[1.3rem] top-2 size-2 rounded-full border border-hairline-2 bg-surface" aria-hidden />
                <span className="text-mist">{activityLabel(a.kind)}</span>
                <time dateTime={a.time} className="tnum shrink-0 font-mono text-xs text-faint">{a.time.slice(11, 19)}</time>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <section aria-labelledby="dash-recs">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 id="dash-recs" className="text-sm font-semibold">{t('dash.recs')}</h2>
          <Button variant="quiet" onClick={() => goto('recommendations')}>{t('dash.viewAll')}</Button>
        </div>
        <RecsList env={env} recs={recs} limit={3} compact onSimulate={onSimulate} onActivity={onActivity} />
      </section>

      <div className="grid gap-4 lg:grid-cols-12 lg:items-start">
        <Panel className="lg:col-span-8" title={t('dash.graph')} action={<Button variant="quiet" onClick={() => goto('graph')}>{t('dash.open')}</Button>}>
          <GraphView env={env} path={top} onlyPath sim={sim} selection={selection} onSelect={setSelection} height={440} />
        </Panel>
        <Panel className="lg:col-span-4" title={t('dash.comparison')}>
          {sim ? <MiniComparison sim={sim} /> : <Empty icon="sliders" action={<Button onClick={() => goto('simulation')}>{t('dash.simulate.cta')}</Button>}>{t('dash.comparison.empty')}</Empty>}
        </Panel>
      </div>
    </div>
  )
}

function FindingGroup({ title, hint, list, limit, env, onOpen }: { title: string; hint: string; list: Finding[]; limit: number; env: Environment; onOpen: (f: Finding) => void }) {
  const { t, assetName, num, arrow } = useI18n()
  return (
    <div>
      <div className="mb-2 flex items-baseline gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <span className="tnum rounded bg-raised px-1.5 text-xs text-mist">{list.length}</span>
        <span className="hidden text-xs text-faint sm:inline">{hint}</span>
      </div>
      {list.length === 0 ? (
        <p className="text-sm text-faint">{t('dash.findings.none')}</p>
      ) : (
        <ul className="space-y-1.5">
          {list.slice(0, limit).map((f) => {
            const rel = f.relationship_id ? findRel(env, f.relationship_id) : undefined
            const label = f.kind === 'attack_path'
              ? t('finding.attack_path', { target: assetName(findAsset(env, f.target ?? '')) })
              : t('finding.unjustified_access', { privilege: t(`priv.${f.privilege}`), source: assetName(findAsset(env, rel?.source ?? '')), target: assetName(findAsset(env, rel?.target ?? '')), arrow })
            return (
              <li key={f.id}>
                <button onClick={() => onOpen(f)} className="flex w-full items-center gap-3 rounded-md border border-hairline bg-raised/50 py-2 pe-3 ps-0 text-start hover:bg-raised max-sm:min-h-12">
                  <span className={`ms-0 w-1 self-stretch rounded-s ${SEV[f.severity].bar}`} aria-hidden />
                  <span className="min-w-0 flex-1 text-sm">{label}</span>
                  <SeverityBadge severity={f.severity} />
                  {f.classification && <span className="hidden sm:inline"><EvidenceTag level={f.classification} /></span>}
                  {f.score !== undefined && <span className="tnum w-10 text-end font-mono text-xs text-mist">{num(f.score)}</span>}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function MiniComparison({ sim }: { sim: SimResult }) {
  const { t, num, arrow } = useI18n()
  return (
    <div className="space-y-3" data-testid="mini-comparison">
      <div className="flex items-end justify-between gap-2">
        <div><p className="text-xs text-faint">{t('sim.before')}</p><p className="tnum text-3xl font-semibold">{num(sim.before.attack_paths)}</p></div>
        <span className="pb-2 text-faint" aria-hidden>{arrow}</span>
        <div className="text-end"><p className="text-xs text-faint">{t('sim.after')}</p><p className="tnum text-3xl font-semibold text-teal">{num(sim.after.attack_paths)}</p></div>
      </div>
      <p className="text-xs text-mist">{t('kpi.paths')} · {t('sim.eliminated')}: {sim.paths_eliminated.length}</p>
      <StackedBar label={t('sim.after')} segments={SEVERITIES.map((k) => ({ value: sim.after.severity_distribution[k], className: SEV[k].bar }))} />
    </div>
  )
}
