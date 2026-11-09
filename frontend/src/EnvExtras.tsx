import { useEffect, useState } from 'react'
import { api } from './api'
import { findAsset } from './helpers'
import { useI18n } from './i18n'
import { useMode } from './mode'
import type { Activity, AttackScenario, Environment, ServiceDependency } from './types'
import { Button, Empty, Id, Pips, Spinner } from './ui'

/** Business services and the access they depend on: what a defensive change could break. Declared by the data author. */
export function ServicesPanel({ env }: { env: Environment }) {
  const { t, lang, assetName, arrow } = useI18n()
  const [list, setList] = useState<ServiceDependency[] | null>(null)
  useEffect(() => { api.services().then(setList).catch(() => setList([])) }, [env])
  if (!list) return <Spinner label={t('state.loading')} />
  if (list.length === 0) return <div className="p-4"><Empty icon="layers">{t('svc.none')}</Empty></div>
  return (
    <div className="space-y-3 p-4" data-testid="services">
      <p className="text-sm text-mist">{t('svc.intro')}</p>
      <ul className="grid gap-3 lg:grid-cols-2">
        {list.map((s) => (
          <li key={s.id} className="rounded-lg border border-hairline bg-surface p-3">
            <div className="flex flex-wrap items-center gap-2">
              <b className="text-sm">{lang === 'ar' ? s.name_ar : s.name}</b>
              <Pips n={s.criticality} />
              <span className="text-xs text-faint">RTO {s.rto_hours} h</span>
              <Id>{s.id}</Id>
              {s.exposed_dependencies > 0 && <span className="ms-auto rounded border border-high/45 bg-high/10 px-1.5 py-0.5 text-xs text-high-fg">{t('svc.exposed', { n: s.exposed_dependencies })}</span>}
            </div>
            <p className="mt-1 text-xs text-mist">{lang === 'ar' ? s.description_ar : s.description}</p>
            <h4 className="mt-2 text-xs font-semibold text-faint">{t('svc.requires')}</h4>
            <ul className="mt-1 space-y-1">
              {s.access_requirements.map((a) => (
                <li key={a.relationship_id} className="rounded bg-raised/60 px-2 py-1 text-xs">
                  {assetName(findAsset(env, a.source))} <span className="text-faint">{arrow}</span> {t(`rel.${a.type}`)} <span className="text-faint">{arrow}</span> {assetName(findAsset(env, a.target))}
                  <span className="text-faint"> · {t('svc.pathsThrough', { n: a.attack_paths_through })}{a.business_critical ? ` · ${t('detail.bizcritical')}` : ''}</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Named assumed-breach starting points. Activating one only changes which assets are marked compromised (undoable). */
export function ScenariosPanel({ env, onChanged }: { env: Environment; onChanged: () => Promise<void> }) {
  const { t, lang } = useI18n()
  const { readOnly } = useMode()
  const [list, setList] = useState<AttackScenario[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => { api.attackScenarios().then(setList).catch(() => setList([])) }, [env])
  if (!list) return <Spinner label={t('state.loading')} />
  if (list.length === 0) return <div className="p-4"><Empty icon="alert">{t('scn.none')}</Empty></div>
  const activate = async (id: string) => {
    setBusy(true)
    setErr('')
    try {
      await api.activateScenario(id)
      await onChanged()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="space-y-3 p-4" data-testid="scenarios">
      <p className="text-sm text-mist">{t('scn.intro')}</p>
      {readOnly && <p className="rounded-md border border-hairline-2 p-2.5 text-sm text-mist">{t('demo.readonly.note')}</p>}
      <ul className="grid gap-3 lg:grid-cols-2">
        {list.map((s) => (
          <li key={s.id} className={`rounded-lg border p-3 ${s.active ? 'border-teal/60 bg-teal/10' : 'border-hairline bg-surface'}`}>
            <div className="flex flex-wrap items-center gap-2"><b className="text-sm">{lang === 'ar' ? s.name_ar : s.name}</b>{s.active && <span className="rounded border border-teal/50 px-1.5 text-xs text-teal">{t('scn.active')}</span>}</div>
            <p className="mt-1 text-xs text-mist">{lang === 'ar' ? s.description_ar : s.description}</p>
            <p className="mt-1 text-xs text-faint">{t('scn.starts')}: {s.compromised.map((id) => <Id key={id}>{id} </Id>)}</p>
            <Button className="mt-2" disabled={readOnly || busy || !!s.active} onClick={() => void activate(s.id)} data-testid={`scenario-${s.id}`}>{t('scn.activate')}</Button>
          </li>
        ))}
      </ul>
      {err && <p role="alert" className="text-sm text-crit-fg">{err}</p>}
    </div>
  )
}

/** The audit trail of what happened in this instance (kept in SQLite on the server). */
export function AuditPanel({ activity }: { activity: Activity[] }) {
  const { t } = useI18n()
  const label = (kind: string) => (t(`act.${kind}`) === `act.${kind}` ? t('act.other') : t(`act.${kind}`))
  return (
    <div className="space-y-3 p-4" data-testid="audit">
      <p className="text-sm text-mist">{t('audit.intro')}</p>
      {activity.length === 0 ? <Empty icon="list">{t('audit.none')}</Empty> : (
        <ul className="divide-y divide-hairline rounded-lg border border-hairline">
          {activity.slice(0, 50).map((a, i) => (
            <li key={a.time + a.kind + i} className="flex flex-wrap items-baseline justify-between gap-3 px-3 py-2 text-sm">
              <span>{label(a.kind)}</span>
              <time dateTime={a.time} className="tnum font-mono text-xs text-faint" dir="ltr">{a.time.slice(0, 19).replace('T', ' ')}</time>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
