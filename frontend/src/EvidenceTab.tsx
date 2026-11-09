import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { findAsset } from './helpers'
import { useI18n } from './i18n'
import { Icon } from './icons'
import type { EvidenceOverview, Environment } from './types'
import { Button, Check, EvidenceTag, Id, Panel, Spinner, controlCls } from './ui'

const CLASSES = ['validated', 'observed', 'inferred', 'theoretical']
const PAGE = 60

/** Provenance of every relationship. All of it is declared by the data author; ATHAR never verifies or upgrades it. */
export default function EvidenceTab({ env }: { env: Environment }) {
  const { t, lang, assetName, arrow, num } = useI18n()
  const [data, setData] = useState<EvidenceOverview | null>(null)
  const [err, setErr] = useState('')
  const [cls, setCls] = useState('all')
  const [onPath, setOnPath] = useState(false)
  const [stale, setStale] = useState(false)
  const [q, setQ] = useState('')
  const [limit, setLimit] = useState(PAGE)

  useEffect(() => {
    let live = true
    setData(null)
    api.evidence().then((d) => live && setData(d)).catch((e) => live && setErr(e instanceof Error ? e.message : String(e)))
    return () => { live = false }
  }, [env])

  const rows = useMemo(() => {
    if (!data) return []
    const s = q.trim().toLowerCase()
    return data.relationships.filter((r) => {
      if (cls !== 'all' && r.evidence !== cls) return false
      if (onPath && r.attack_paths_through === 0) return false
      if (stale && !r.stale) return false
      if (!s) return true
      const a = findAsset(env, r.source), b = findAsset(env, r.target)
      return `${r.id} ${r.type} ${r.evidence_source} ${a?.name ?? ''} ${a?.name_ar ?? ''} ${b?.name ?? ''} ${b?.name_ar ?? ''}`.toLowerCase().includes(s)
    })
  }, [data, cls, onPath, stale, q, env])

  if (err) return <p role="alert" className="text-sm text-crit-fg">{err}</p>
  if (!data) return <Spinner label={t('state.loading')} />
  const s = data.summary

  return (
    <div className="space-y-4" data-testid="evidence">
      <p className="flex gap-2 rounded-lg border border-hairline-2 bg-raised/50 p-3 text-sm text-mist"><Icon name="info" size={16} className="mt-0.5 text-teal" />{t('evx.honesty')}</p>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="evidence-summary">
        {CLASSES.map((c) => (
          <Panel key={c}>
            <EvidenceTag level={c} />
            <p className="tnum mt-2 text-2xl font-semibold" dir="ltr">{s.by_evidence[c] ?? 0}</p>
            <p className="mt-1 text-xs text-faint">{t(`ev.def.${c}`)}</p>
          </Panel>
        ))}
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Panel title={t('evx.validation')}>
          <ul className="space-y-1 text-sm">
            {Object.entries(s.by_validation).map(([k, v]) => (
              <li key={k} className="flex justify-between gap-2"><span className="text-mist">{t(`val.${k}`)}</span><b className="tnum" dir="ltr" data-testid={`val-${k}`}>{v}</b></li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-faint">{t('evx.validation.note')}</p>
        </Panel>
        <Panel title={t('evx.sources')}>
          <ul className="space-y-1 text-sm">{Object.entries(s.by_source).map(([k, v]) => <li key={k} className="flex justify-between gap-2"><Id>{k}</Id><b className="tnum" dir="ltr">{v}</b></li>)}</ul>
        </Panel>
        <Panel title={t('evx.freshness')}>
          <ul className="space-y-1 text-sm">
            <li className="flex justify-between gap-2"><span className="text-mist">{t('evx.stale', { n: s.stale_after_days })}</span><b className="tnum" dir="ltr">{s.stale}</b></li>
            <li className="flex justify-between gap-2"><span className="text-mist">{t('evx.undated')}</span><b className="tnum" dir="ltr">{s.undated}</b></li>
            <li className="flex justify-between gap-2"><span className="text-mist">{t('evx.onPaths')}</span><b className="tnum" dir="ltr">{s.on_attack_paths}</b></li>
            <li className="flex justify-between gap-2"><span className="text-mist">{t('evx.weakOnPaths')}</span><b className="tnum" dir="ltr">{s.weak_on_paths}</b></li>
          </ul>
        </Panel>
      </div>

      <Panel flush>
        <div className="flex flex-wrap items-center gap-3 border-b border-hairline p-3">
          <select aria-label={t('evx.filter.class')} value={cls} onChange={(e) => { setCls(e.target.value); setLimit(PAGE) }} className={`${controlCls} !w-auto`}>
            <option value="all">{t('graph.filter.all')}</option>
            {CLASSES.map((c) => <option key={c} value={c}>{t(`cls.${c}`)}</option>)}
          </select>
          <Check label={t('evx.filter.onPath')} checked={onPath} onChange={setOnPath} />
          <Check label={t('evx.filter.stale')} checked={stale} onChange={setStale} />
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('env.search')} aria-label={t('env.search')} className={`${controlCls} !w-auto min-w-0 flex-1 sm:max-w-xs sm:flex-none`} />
          <span className="tnum ms-auto text-xs text-faint">{rows.length} / {s.total}</span>
        </div>
        <ul className="grid gap-px bg-hairline md:grid-cols-2" data-testid="evidence-rows">
          {rows.slice(0, limit).map((r) => (
            <li key={r.id} className="bg-surface p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <EvidenceTag level={r.evidence} />
                <span className="rounded border border-hairline-2 px-1.5 py-0.5 text-xs text-mist">{t('evx.confidence')}: {t(`conf.${r.confidence}`)}</span>
                {r.stale && <span className="rounded border border-high/45 bg-high/10 px-1.5 py-0.5 text-xs text-high-fg">{t('evx.staleTag')}</span>}
                <Id>{r.id}</Id>
              </div>
              <p className="mt-1.5">{assetName(findAsset(env, r.source))} <span className="text-faint">{arrow}</span> <span className="text-mist">{t(`rel.${r.type}`)}</span> <span className="text-faint">{arrow}</span> {assetName(findAsset(env, r.target))}</p>
              <dl className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs text-mist">
                <div><dt className="inline text-faint">{t('evx.source')}: </dt><dd className="inline"><Id>{r.evidence_source}</Id></dd></div>
                <div><dt className="inline text-faint">{t('evx.collected')}: </dt><dd className="inline" dir="ltr">{r.collected_at ? r.collected_at.slice(0, 10) : t('evx.none')}</dd></div>
                <div><dt className="inline text-faint">{t('evx.validationOne')}: </dt><dd className="inline">{t(`val.${r.validation}`)}</dd></div>
                <div><dt className="inline text-faint">{t('evx.pathsThrough')}: </dt><dd className="tnum inline" dir="ltr">{num(r.attack_paths_through)}</dd></div>
              </dl>
              {(lang === 'ar' ? r.rationale_ar : r.rationale) && <p className="mt-1.5 text-xs text-mist">{lang === 'ar' ? r.rationale_ar : r.rationale}</p>}
            </li>
          ))}
        </ul>
        {rows.length === 0 && <p className="p-4 text-sm text-faint">{t('env.noMatches')}</p>}
        {rows.length > limit && <div className="border-t border-hairline p-3"><Button onClick={() => setLimit(limit + PAGE)}>{t('evx.more')}</Button></div>}
      </Panel>
    </div>
  )
}
