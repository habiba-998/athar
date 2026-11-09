import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import GraphView, { type Selection } from './GraphView'
import { findAsset, findRel, pathEvidence, relText, routeNames } from './helpers'
import { useMediaQuery, useNarrow } from './hooks'
import { useI18n } from './i18n'
import { Icon, TYPE_ICON } from './icons'
import RouteTrace from './RouteTrace'
import type { Analysis, AttackPath, Environment, Explanation, Severity, SimResult } from './types'
import { Button, Check, Empty, EvidenceLegend, EvidenceTag, Id, Panel, Pips, SEV, SEVERITIES, SeverityBadge } from './ui'

interface Props {
  env: Environment
  analysis: Analysis
  sim: SimResult | null
  pathId: string | null
  setPathId: (id: string | null) => void
  selection: Selection
  setSelection: (s: Selection) => void
  onActivity: () => void
}

const TYPES = ['user', 'service_account', 'group', 'server', 'database', 'cloud', 'identity_provider', 'control']
const EVIDENCE = ['validated', 'observed', 'inferred', 'theoretical']

export default function GraphTab({ env, analysis, sim, pathId, setPathId, selection, setSelection, onActivity }: Props) {
  const { t, lang } = useI18n()
  const narrow = useNarrow()
  const wide = useMediaQuery('(min-width: 1280px)')
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [onlyPath, setOnlyPath] = useState(false)
  const [hiddenEv, setHiddenEv] = useState<Set<string>>(new Set())
  const [query, setQuery] = useState('')
  const [expanded, setExpanded] = useState(false)
  const [vh, setVh] = useState(() => (typeof window === 'undefined' ? 800 : window.innerHeight))
  const [sev, setSev] = useState<Severity | 'all'>('all')
  const graphRef = useRef<HTMLDivElement>(null)
  const path = analysis.paths.find((p) => p.id === pathId) ?? null

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: analysis.paths.length }
    for (const k of SEVERITIES) c[k] = analysis.paths.filter((p) => p.severity === k).length
    return c
  }, [analysis.paths])
  const shown = sev === 'all' ? analysis.paths : analysis.paths.filter((p) => p.severity === sev)

  // On phones the graph sits below the list: bring it into view when a path is chosen.
  useEffect(() => {
    if (narrow && pathId) graphRef.current?.scrollIntoView({ block: 'start' })
  }, [narrow, pathId])

  // Choosing a path isolates it (readable at any width); once the user toggles the checkbox themselves, their choice sticks.
  const manualIsolate = useRef(false)
  useEffect(() => {
    if (!manualIsolate.current) setOnlyPath(!!pathId)
  }, [pathId])

  useEffect(() => {
    const onResize = () => setVh(window.innerHeight)
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setExpanded(false) }
    window.addEventListener('resize', onResize)
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('resize', onResize); window.removeEventListener('keydown', onKey) }
  }, [])
  const toggleEv = (e: string) =>
    setHiddenEv((h) => {
      const n = new Set(h)
      if (n.has(e)) n.delete(e)
      else n.add(e)
      return n
    })

  const toggle = (type: string) =>
    setHidden((h) => {
      const n = new Set(h)
      if (n.has(type)) n.delete(type)
      else n.add(type)
      return n
    })

  return (
    <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)] xl:grid-cols-[320px_minmax(0,1fr)_380px]">
      <Panel title={t('graph.paths')} hint={t('graph.paths.hint', { n: analysis.paths.length })} flush className="lg:self-start">
        <div role="group" aria-label={t('graph.filter.severity')} className="flex flex-wrap gap-1.5 border-b border-hairline p-3">
          {(['all', ...SEVERITIES] as const).map((k) => (
            <button key={k} aria-pressed={sev === k} onClick={() => setSev(k)}
              className={`inline-flex min-h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium max-sm:min-h-11 ${sev === k ? 'border-teal/60 bg-teal/10 text-teal' : 'border-hairline-2 text-mist hover:bg-raised'}`}>
              {k === 'all' ? t('graph.filter.all') : t(`sev.${k}`)} <span className="tnum text-faint">{counts[k]}</span>
            </button>
          ))}
        </div>
        {shown.length === 0 ? (
          <div className="p-3"><Empty icon="shield">{t('graph.noPaths')}</Empty></div>
        ) : (
          <ul aria-label={t('graph.paths')} className="max-h-80 divide-y divide-hairline overflow-y-auto xl:max-h-[calc(100dvh-16rem)]">
            {shown.map((p) => <PathItem key={p.id} p={p} env={env} active={p.id === pathId} onClick={() => setPathId(p.id === pathId ? null : p.id)} />)}
          </ul>
        )}
      </Panel>

      <div ref={graphRef} className={`min-w-0 scroll-mt-16 space-y-4 ${expanded ? 'fixed inset-0 z-40 overflow-y-auto bg-abyss p-3' : ''}`} data-testid="graph-region" data-expanded={expanded || undefined}>
        <Panel flush>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-hairline px-3 py-2">
            <details className="group relative">
              <summary className="flex min-h-9 cursor-pointer list-none items-center gap-2 rounded-md px-2 text-sm text-mist hover:bg-raised hover:text-cloud max-sm:min-h-11">
                <Icon name="filter" size={16} /> {t('graph.filters')}
                <Icon name="chevron" size={14} className="transition-transform group-open:rotate-90" />
              </summary>
              <div className="absolute start-0 z-30 mt-1 grid min-w-56 gap-0.5 rounded-lg border border-hairline-2 bg-raised p-2 shadow-xl">
                {TYPES.map((ty) => <Check key={ty} label={t(`type.${ty}`)} checked={!hidden.has(ty)} onChange={() => toggle(ty)} />)}
              </div>
            </details>
            <details className="group relative">
              <summary data-testid="evidence-filter-toggle" className="flex min-h-9 cursor-pointer list-none items-center gap-2 rounded-md px-2 text-sm text-mist hover:bg-raised hover:text-cloud max-sm:min-h-11">
                <Icon name="layers" size={16} /> {t('graph.filters.evidence')}
                <Icon name="chevron" size={14} className="transition-transform group-open:rotate-90" />
              </summary>
              <div className="absolute start-0 z-30 mt-1 grid min-w-56 gap-0.5 rounded-lg border border-hairline-2 bg-raised p-2 shadow-xl" data-testid="evidence-filter">
                {EVIDENCE.map((ev) => <Check key={ev} label={t(`cls.${ev}`)} checked={!hiddenEv.has(ev)} onChange={() => toggleEv(ev)} />)}
              </div>
            </details>
            <div className="relative min-w-0 flex-1 sm:max-w-xs">
              <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('graph.search')} aria-label={t('graph.search')} data-testid="graph-search" className="block min-h-9 w-full rounded-md border border-hairline-2 bg-abyss px-3 text-sm text-cloud placeholder:text-faint max-sm:min-h-11" />
            </div>
            <Button variant="quiet" icon="expand" aria-pressed={expanded} onClick={() => setExpanded((v) => !v)} data-testid="graph-fullscreen">{expanded ? t('graph.fullscreen.exit') : t('graph.fullscreen')}</Button>
            <div className="ms-auto"><Check label={t('graph.onlyPath')} checked={onlyPath && !!path} disabled={!path} onChange={(v) => { manualIsolate.current = true; setOnlyPath(v) }} /></div>
          </div>
          <div className="p-3">
            <GraphView env={env} path={path} sim={sim} selection={selection} onSelect={setSelection} hiddenTypes={hidden} hiddenEvidence={hiddenEv} query={query} onlyPath={onlyPath} height={expanded ? Math.max(360, vh - 230) : narrow ? 520 : wide ? 640 : 520} />
          </div>
          <div className="space-y-2 border-t border-hairline px-3 py-3">
            <GraphLegend />
            <p className="text-xs text-faint">{t('graph.keyboard')}</p>
            <EvidenceLegend />
          </div>
        </Panel>
      </div>

      <div className="min-w-0 space-y-4 lg:col-span-2 xl:col-span-1">
        {path ? (
          <PathPanel env={env} path={path} lang={lang} onActivity={onActivity} onClose={() => setPathId(null)} />
        ) : selection ? null : (
          <Panel title={t('detail.panel')}><Empty icon="graph">{t('graph.select')}</Empty></Panel>
        )}
        {selection && <SelectionPanel env={env} selection={selection} clear={() => setSelection(null)} />}
      </div>
    </div>
  )
}

function PathItem({ p, env, active, onClick }: { p: AttackPath; env: Environment; active: boolean; onClick: () => void }) {
  const { assetName, num, arrow } = useI18n()
  const names = routeNames(env, p.nodes, assetName)
  return (
    <li>
      <button onClick={onClick} aria-pressed={active}
        className={`flex w-full items-stretch gap-3 py-3 pe-3 ps-0 text-start transition-colors ${active ? 'bg-teal/10' : 'hover:bg-raised'}`}>
        <span className={`w-1 shrink-0 rounded-e ${SEV[p.severity].bar} ${active ? '' : 'opacity-70'}`} aria-hidden />
        <span className="min-w-0 flex-1 space-y-2">
          <span className="flex flex-wrap items-center gap-1.5">
            <SeverityBadge severity={p.severity} />
            <EvidenceTag level={p.classification} />
            <span className="tnum ms-auto font-mono text-xs text-mist">{num(p.score)}</span>
          </span>
          <span className="block text-sm font-medium">{assetName(findAsset(env, p.target))}</span>
          <RouteTrace compact names={names} evidence={pathEvidence(p)} severity={p.severity} vertical={false} />
          <span className="block text-xs leading-snug text-faint">{names.join(` ${arrow} `)}</span>
        </span>
      </button>
    </li>
  )
}

function GraphLegend() {
  const { t } = useI18n()
  const sample = (dash?: string, color = 'currentColor') => (
    <svg width="26" height="8" viewBox="0 0 26 8" aria-hidden="true"><line x1="0" y1="4" x2="26" y2="4" stroke={color} strokeWidth="2" strokeDasharray={dash} /></svg>
  )
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-mist">
      <li className="flex items-center gap-2 text-teal">{sample()} <span className="text-mist">{t('cls.validated')}</span></li>
      <li className="flex items-center gap-2 text-teal">{sample('12 3 2 3')} <span className="text-mist">{t('cls.observed')}</span></li>
      <li className="flex items-center gap-2 text-teal">{sample('8 5')} <span className="text-mist">{t('cls.inferred')}</span></li>
      <li className="flex items-center gap-2 text-teal">{sample('2 6')} <span className="text-mist">{t('cls.theoretical')}</span></li>
      <li className="flex items-center gap-2"><span className="size-2.5 rounded-full bg-crit" aria-hidden />{t('graph.legend.compromised')}</li>
      <li className="flex items-center gap-2"><span className="h-3 w-1 rounded-sm bg-high" aria-hidden />{t('graph.legend.sensitive')}</li>
      <li className="flex items-center gap-2">{sample(undefined, '#ef5b6b')} {t('graph.legend.removed')}</li>
      <li className="flex items-center gap-2">{sample(undefined, '#f2a03d')} {t('graph.legend.mitigated')}</li>
    </ul>
  )
}

function SelectionPanel({ env, selection, clear }: { env: Environment; selection: NonNullable<Selection>; clear: () => void }) {
  const { t, assetName, lang } = useI18n()
  const rel = selection.kind === 'rel' ? findRel(env, selection.id) : undefined
  const asset = selection.kind === 'asset' ? findAsset(env, selection.id) : undefined
  return (
    <Panel title={asset ? assetName(asset) : t('detail.relationship')} action={<Button variant="quiet" icon="x" onClick={clear}>{t('graph.clear')}</Button>}>
      <div className="space-y-3 text-sm" data-testid="selection-detail">
        {asset && (
          <>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-mist">
              <span className="inline-flex items-center gap-1.5"><Icon name={TYPE_ICON[asset.type] ?? 'server'} size={16} />{t(`type.${asset.type}`)}</span>
              <span className="inline-flex items-center gap-1.5">{t('detail.criticality')} <Pips n={asset.criticality} /></span>
              <span>{t('detail.exposure')}: {t(`exp.${asset.exposure}`)}</span>
              <Id>{asset.id}</Id>
            </div>
            <p className="text-mist">{lang === 'ar' ? asset.description_ar : asset.description}</p>
            {(['outgoing', 'incoming'] as const).map((dirn) => {
              const list = env.relationships.filter((r) => (dirn === 'outgoing' ? r.source : r.target) === asset.id)
              return (
                <div key={dirn}>
                  <h3 className="mb-1.5 text-xs font-semibold text-faint">{t(`detail.${dirn}`)} <span className="tnum">({list.length})</span></h3>
                  <ul className="space-y-1.5">
                    {list.map((r) => (
                      <li key={r.id} className="rounded-md bg-raised/60 p-2">
                        <div>{relText(env, r, t, assetName)}</div>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-mist">{t(`priv.${r.privilege}`)} <EvidenceTag level={r.evidence} />{r.disabled && <span>· {t('rel.status.disabled')}</span>}</div>
                      </li>
                    ))}
                    {list.length === 0 && <li className="text-faint">—</li>}
                  </ul>
                </div>
              )
            })}
          </>
        )}
        {rel && (
          <>
            <p className="font-medium">{relText(env, rel, t, assetName)}</p>
            <dl className="grid grid-cols-3 gap-3">
              <div><dt className="text-xs text-faint">{t('detail.privilege')}</dt><dd className="mt-0.5">{t(`priv.${rel.privilege}`)}</dd></div>
              <div><dt className="text-xs text-faint">{t('detail.evidence')}</dt><dd className="mt-0.5"><EvidenceTag level={rel.evidence} /></dd></div>
              <div><dt className="text-xs text-faint">{t('detail.bizcritical')}</dt><dd className="mt-0.5">{rel.business_critical ? t('yes') : t('no')}</dd></div>
            </dl>
            <p><span className="text-faint">{t('detail.legit')}: </span>{(lang === 'ar' ? rel.legitimate_use_ar : rel.legitimate_use) ?? t('detail.nolegit')}</p>
          </>
        )}
      </div>
    </Panel>
  )
}

function PathPanel({ env, path, lang, onActivity, onClose }: { env: Environment; path: AttackPath; lang: 'en' | 'ar'; onActivity: () => void; onClose: () => void }) {
  const { t, assetName, num, arrow } = useI18n()
  const [exp, setExp] = useState<Explanation | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  // a different path invalidates the explanation shown for the previous one
  useEffect(() => { setExp(null); setErr('') }, [path.id])

  const explain = async () => {
    setBusy(true)
    setErr('')
    try {
      setExp(await api.explain('path', path.id, lang))
      onActivity()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel title={t('path.why')} action={<Button variant="quiet" icon="x" onClick={onClose}>{t('graph.clear')}</Button>}>
      <div className="space-y-5 text-sm" data-testid="path-detail">
        <div>
          <div className="flex flex-wrap items-center gap-1.5">
            <SeverityBadge severity={path.severity} />
            <EvidenceTag level={path.classification} />
          </div>
          <p className="mt-3 flex items-baseline gap-2">
            <bdi dir="ltr"><span className={`tnum text-3xl font-semibold ${SEV[path.severity].text}`}>{num(path.score)}</span><span className="text-faint"> / 100</span></bdi>
            <span className="text-faint">· {path.steps.length} {t('hops')}</span>
          </p>
        </div>

        <div>
          <h3 className="mb-2 text-xs font-semibold text-faint">{t('path.sequence')}</h3>
          <ol className="space-y-2">
            {path.steps.map((s, i) => {
              const r = findRel(env, s.relationship_id)
              return (
                <li key={s.relationship_id} className="flex gap-3 rounded-md border border-hairline bg-raised/50 p-2.5">
                  <span className="tnum grid size-6 shrink-0 place-items-center rounded-full border border-hairline-2 font-mono text-xs text-mist">{i + 1}</span>
                  <span className="min-w-0">
                    <span className="block">{r ? relText(env, r, t, assetName) : s.relationship_id}</span>
                    <span className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-mist">{t(`priv.${s.privilege}`)} <EvidenceTag level={s.evidence} /><Id>{s.relationship_id}</Id>
                      {path.weakest_hop?.relationship_id === s.relationship_id && <span className="rounded border border-high/45 bg-high/10 px-1.5 text-high-fg" data-testid="weakest-hop">{t('path.weakest')}</span>}</span>
                    {s.evidence_source && <span className="mt-1 block text-xs text-faint">{t('evx.source')}: <Id>{s.evidence_source}</Id> · {t('evx.confidence')}: {t(`conf.${s.confidence ?? 'low'}`)}{r?.collected_at ? ` · ${t('evx.collected')}: ${r.collected_at.slice(0, 10)}` : ''}</span>}
                  </span>
                </li>
              )
            })}
          </ol>
        </div>

        <div>
          {path.drivers && path.drivers.length > 0 && <p className="mb-2 text-xs text-mist" data-testid="path-drivers">{t('path.drivers')}: {path.drivers.map((d) => t(`factor.${d}`)).join(', ')}</p>}
          <h3 className="mb-1 text-xs font-semibold text-faint">{t('path.factors')}</h3>
          <p className="mb-2 text-xs text-faint">{t('path.factors.help')}</p>
          <ul className="space-y-2">
            {path.factors.map((f) => (
              <li key={f.code}>
                <div className="flex items-baseline justify-between gap-2"><span className="text-mist">{t(`factor.${f.code}`)}</span><span className="tnum font-mono text-xs">{f.value}</span></div>
                <div className="mt-1 h-1.5 rounded-sm bg-hairline"><div className="grow h-full rounded-sm bg-teal/80" style={{ width: `${Math.min(100, f.value * 100)}%` }} /></div>
              </li>
            ))}
          </ul>
        </div>

        <Button variant="primary" icon="info" onClick={explain} disabled={busy} className="w-full">{busy ? t('path.explaining') : t('path.explain')}</Button>
        {err && <p role="alert" className="text-crit-fg">{err}</p>}
        {exp && (
          <div className="space-y-3 border-t border-hairline pt-4" data-testid="explanation">
            <h3 className="text-xs font-semibold text-faint">{t('explain.evidence')}</h3>
            <p className="text-mist">{exp.evidence.route.join(` ${arrow} `)}</p>
            <h3 className="text-xs font-semibold text-faint">{t('explain.template')}</h3>
            <p>{exp.template_explanation}</p>
            <section aria-label={t('ai.label')} className="rounded-md border border-dashed border-hairline-2 p-3" data-testid="ai-section">
              <h3 className="flex items-center gap-1.5 text-xs font-semibold text-faint"><Icon name="info" size={14} />{t('ai.label')}</h3>
              {exp.ai_explanation ? (
                <p className="mt-1.5" data-testid="ai-text">{exp.ai_explanation}</p>
              ) : (
                <p className="mt-1.5 text-mist" data-testid="ai-fallback">
                  {exp.ai_status === 'ai_disabled' ? t('ai.off') : exp.ai_status === 'ai_not_configured' ? t('ai.notConfigured') : t('ai.unavailable')}
                </p>
              )}
            </section>
          </div>
        )}
      </div>
    </Panel>
  )
}
