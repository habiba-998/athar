import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, tokenStore } from './api'
import Dashboard from './Dashboard'
import AssumptionsTab from './AssumptionsTab'
import EnvTab from './EnvTab'
import EvidenceTab from './EvidenceTab'
import GraphTab from './GraphTab'
import type { Selection } from './GraphView'
import { actionKey } from './helpers'
import { useI18n } from './i18n'
import { Icon, type IconName } from './icons'
import { ModeContext } from './mode'
import PlansTab from './PlansTab'
import RecsList from './RecsTab'
import SimTab from './SimTab'
import type { Activity, AiStatus, AuthStatus, Analysis, EnvMeta, Environment, Recommendation, SimAction, SimRecord, SimResult } from './types'
import { Button, Dialog, Field, Panel, Spinner, controlCls } from './ui'

type Tab = 'dashboard' | 'graph' | 'simulation' | 'recommendations' | 'evidence' | 'environment'
const TABS: { id: Tab; icon: IconName }[] = [
  { id: 'dashboard', icon: 'dashboard' },
  { id: 'graph', icon: 'graph' },
  { id: 'simulation', icon: 'sliders' },
  { id: 'recommendations', icon: 'bulb' },
  { id: 'evidence', icon: 'flask' },
  { id: 'environment', icon: 'database' },
]

interface Data {
  env: Environment
  analysis: Analysis
  recs: Recommendation[]
}

/** The brand mark is the product's own motif: a tiny route trace from a compromised start to a sensitive target. */
function BrandMark() {
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" aria-hidden="true">
      <path d="M6 24L15 17" stroke="#34d1bf" strokeWidth="2" strokeLinecap="round" />
      <path d="M15 17L25 9" stroke="#34d1bf" strokeWidth="2" strokeLinecap="round" strokeDasharray="1.5 3.5" />
      <circle cx="6" cy="24" r="3.2" fill="#ef5b6b" />
      <circle cx="15" cy="17" r="3" fill="#060a14" stroke="#34d1bf" strokeWidth="2" />
      <rect x="21.8" y="5.8" width="6.4" height="6.4" rx="1.2" transform="rotate(45 25 9)" fill="#34d1bf" />
    </svg>
  )
}

export default function App() {
  const { t, lang, setLang } = useI18n()
  const [tab, setTab] = useState<Tab>('dashboard')
  const [recView, setRecView] = useState<'recs' | 'plans'>('recs')
  const [evView, setEvView] = useState<'evidence' | 'assumptions'>('evidence')
  const [auth, setAuth] = useState<AuthStatus | null>(null)
  const [canWrite, setCanWrite] = useState(true)
  const [adminOpen, setAdminOpen] = useState(false)
  const [data, setData] = useState<Data | null>(null)
  const [meta, setMeta] = useState<EnvMeta | null>(null)
  const [ai, setAi] = useState<AiStatus | null>(null)
  const [activity, setActivity] = useState<Activity[]>([])
  const [history, setHistory] = useState<SimRecord[]>([])
  const [loadError, setLoadError] = useState('')
  const [needToken, setNeedToken] = useState(false)
  const [tokenError, setTokenError] = useState(false)
  const [pathId, setPathId] = useState<string | null>(null)
  const [selection, setSelection] = useState<Selection>(null)
  const [queue, setQueue] = useState<SimAction[]>([])
  const [sim, setSim] = useState<SimResult | null>(null)
  const [simBusy, setSimBusy] = useState(false)
  const [simError, setSimError] = useState('')

  const refreshActivity = useCallback(() => {
    api.activity().then(setActivity).catch(() => undefined)
    api.simulations().then(setHistory).catch(() => undefined)
  }, [])

  const load = useCallback(async () => {
    setLoadError('')
    try {
      const auth = await api.authStatus()
      setAuth(auth)
      if (auth.token_required && !tokenStore.get()) {
        setNeedToken(true)
        return
      }
      const [env, analysis, recs, act, m, hist, aiState] = await Promise.all([
        api.environment(), api.analysis(), api.recommendations(), api.activity(), api.envMeta(), api.simulations(), api.aiStatus(),
      ])
      setData({ env, analysis, recs })
      setActivity(act)
      setMeta(m)
      setHistory(hist)
      setAi(aiState)
      setNeedToken(false)
      api.whoami().then((w) => setCanWrite(w.can_write)).catch(() => setCanWrite(false))
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        tokenStore.clear()
        setTokenError(true)
        setNeedToken(true)
        return
      }
      setLoadError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  /** After any environment edit: reload everything and drop state that described the old graph. */
  const onEnvChanged = useCallback(async () => {
    setQueue([])
    setSim(null)
    setSimError('')
    setPathId(null)
    setSelection(null)
    await load()
  }, [load])

  const run = async (actions: SimAction[]) => {
    setSimBusy(true)
    setSimError('')
    try {
      setSim(await api.simulate(actions))
      refreshActivity()
    } catch (e) {
      setSim(null)
      setSimError(e instanceof Error ? e.message : String(e))
    } finally {
      setSimBusy(false)
    }
  }

  const reset = () => {
    setQueue([])
    setSim(null)
    setSimError('')
  }

  const undo = () => {
    const next = queue.slice(0, -1)
    setQueue(next)
    setSimError('')
    if (next.length === 0) setSim(null)
    else if (sim) void run(next)
  }

  const viewRecord = async (id: number) => {
    setSimError('')
    try {
      setSim(await api.simulationRecord(id))
    } catch (e) {
      setSimError(e instanceof Error ? e.message : String(e))
    }
  }

  const simulatePlan = (actions: SimAction[]) => {
    setQueue(actions)
    setSim(null)
    setTab('simulation')
  }

  const submitAdmin = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const v = String(new FormData(e.currentTarget).get('admin') ?? '').trim()
    if (v) tokenStore.set(v)
    else tokenStore.clear()
    setAdminOpen(false)
    void load()
  }

  const readOnly = !!auth?.read_only && !canWrite
  const simulateAction = (a: SimAction) => {
    setQueue((q) => (q.some((x) => actionKey(x) === actionKey(a)) ? q : [...q, a]))
    setSim(null)
    setTab('simulation')
  }

  const openPath = (id: string) => {
    setPathId(id)
    setTab('graph')
  }

  const submitToken = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const v = String(new FormData(e.currentTarget).get('token') ?? '').trim()
    if (!v) return
    tokenStore.set(v)
    setTokenError(false)
    setNeedToken(false)
    void load()
  }

  return (
    <ModeContext.Provider value={{ mode: auth?.mode ?? 'local', readOnly }}>
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:start-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-teal focus:px-3 focus:py-2 focus:text-teal-ink">
        {t('a11y.skip')}
      </a>
      {/* No backdrop-filter on the header: it would turn the phone bottom bar (position: fixed) into a header-relative box. */}
      <header className="sticky top-0 z-20 border-b border-hairline bg-abyss">
        <div className="mx-auto flex min-h-14 max-w-[1440px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2">
          <div className="flex items-center gap-2.5">
            <BrandMark />
            <div>
              <div className="text-[17px] font-semibold leading-none" style={{ letterSpacing: '0.2em' }} dir="ltr">ATHAR</div>
              <div className="mt-1 hidden text-xs leading-none text-faint sm:block">{t('app.tagline')}</div>
            </div>
          </div>

          <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-[1fr_1fr_1fr_1.35fr_1fr_1.1fr] border-t border-hairline bg-surface md:static md:z-auto md:order-none md:flex md:gap-1 md:border-0 md:bg-transparent">
            {TABS.map((k) => {
              const on = tab === k.id
              return (
                <button key={k.id} onClick={() => setTab(k.id)} aria-current={on ? 'page' : undefined}
                  className={`relative flex min-h-14 flex-col items-center justify-center gap-1 px-0.5 text-[10.5px] font-medium leading-tight transition-colors md:min-h-10 md:flex-row md:gap-2 md:rounded-md md:px-3 md:text-sm md:leading-normal ${on ? 'text-teal md:bg-raised' : 'text-mist hover:text-cloud md:hover:bg-raised/60'}`}>
                  <Icon name={k.icon} size={20} className="md:hidden lg:block" />
                  <span className="text-center" data-nav-label>{t(`nav.${k.id}`)}</span>
                  {on && <span className="absolute inset-x-3 top-0 h-0.5 rounded-b bg-teal md:inset-x-3 md:bottom-0 md:top-auto md:rounded-t" aria-hidden />}
                </button>
              )
            })}
          </nav>

          <div className="ms-auto flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-md border border-teal/40 bg-teal/10 px-2 py-1 text-xs font-medium text-teal" data-testid="chip-synthetic"><Icon name="shield" size={13} />{t('chip.synthetic')}</span>
            {auth?.read_only && <span className="inline-flex items-center gap-1.5 rounded-md border border-high/45 bg-high/10 px-2 py-1 text-xs font-medium text-high-fg" data-testid="chip-demo"><Icon name="eye" size={13} />{readOnly ? t('chip.demo') : t('chip.admin')}</span>}
            {auth?.admin_token_supported && <Button variant="quiet" icon="lock" onClick={() => setAdminOpen(true)} data-testid="admin-open">{t('admin.open')}</Button>}
            {ai && <span className="rounded-md border border-hairline-2 px-2 py-1 text-xs text-mist" data-testid="chip-ai">{ai.enabled ? t('chip.ai.on') : t('chip.ai.off')}</span>}
            <Button variant="ghost" icon="globe" onClick={() => setLang(lang === 'en' ? 'ar' : 'en')} lang={lang === 'en' ? 'ar' : 'en'} data-testid="lang-toggle">
              {t('lang.switch')}
            </Button>
          </div>
        </div>
      </header>

      {adminOpen && (
        <Dialog title={t('admin.title')} onClose={() => setAdminOpen(false)}>
          <form onSubmit={submitAdmin} className="space-y-4">
            <p className="text-sm text-mist">{t('admin.help')}</p>
            <Field label={t('auth.token')}>{({ id, describedBy }) => <input id={id} aria-describedby={describedBy} name="admin" type="password" autoComplete="off" className={controlCls} />}</Field>
            <div className="flex flex-wrap justify-end gap-2"><Button type="button" variant="ghost" onClick={() => setAdminOpen(false)}>{t('env.cancel')}</Button><Button type="submit" variant="primary">{t('auth.submit')}</Button></div>
          </form>
        </Dialog>
      )}

      <main id="main" tabIndex={-1} className="mx-auto max-w-[1440px] px-4 pb-24 pt-6 md:pb-10">
        {needToken ? (
          <Panel title={t('auth.title')} className="max-w-lg">
            <form onSubmit={submitToken} className="space-y-4">
              <p className="text-sm text-mist">{t('auth.help')}</p>
              <Field label={t('auth.token')}>
                {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} name="token" type="password" autoComplete="off" required className={controlCls} />}
              </Field>
              {tokenError && <p role="alert" className="text-sm text-crit-fg">{t('auth.invalid')}</p>}
              <Button type="submit" variant="primary">{t('auth.submit')}</Button>
            </form>
          </Panel>
        ) : loadError ? (
          <Panel>
            <div role="alert" className="space-y-3">
              <h2 className="flex items-center gap-2 font-semibold text-crit-fg"><Icon name="alert" size={18} />{t('state.error')}</h2>
              <p className="text-sm text-mist">{t('state.error.hint')}</p>
              <p className="font-mono text-xs text-faint" dir="ltr">{loadError}</p>
              <Button variant="primary" onClick={() => void load()}>{t('state.retry')}</Button>
            </div>
          </Panel>
        ) : !data ? (
          <Spinner label={t('state.loading')} />
        ) : (
          <>
            <div className="mb-5">
              <h1 className="text-xl font-semibold">{t(`nav.${tab}`)}</h1>
              <p className="mt-0.5 text-sm text-mist">{t(`page.${tab}`)}</p>
            </div>
            {tab === 'dashboard' && (
              <Dashboard {...data} activity={activity} sim={sim} selection={selection} setSelection={setSelection} goto={(k) => setTab(k as Tab)} openPath={openPath} onSimulate={simulateAction} onActivity={refreshActivity} />
            )}
            {tab === 'graph' && (
              <GraphTab env={data.env} analysis={data.analysis} sim={sim} pathId={pathId} setPathId={setPathId} selection={selection} setSelection={setSelection} onActivity={refreshActivity} />
            )}
            {tab === 'simulation' && (
              <SimTab env={data.env} queue={queue} setQueue={setQueue} sim={sim} history={history} busy={simBusy} error={simError}
                onRun={() => void run(queue)} onReset={reset} onUndo={undo} onView={(id) => void viewRecord(id)} selection={selection} setSelection={setSelection} />
            )}
            {tab === 'recommendations' && (
              <div className="mx-auto max-w-5xl space-y-4">
                <SubTabs value={recView} onChange={setRecView} items={[['recs', t('sub.recs')], ['plans', t('sub.plans')]]} label={t('nav.recommendations')} />
                {recView === 'plans' ? <PlansTab env={data.env} onSimulatePlan={simulatePlan} /> : <>
                <p className="text-sm text-mist">{t('rec.intro')} {t('rec.priority.help')}</p>
                {(meta?.recommendations_partial || data.analysis.summary.paths_truncated) && (
                  <p role="alert" data-testid="partial-warning" className="flex gap-2 rounded-lg border border-med/50 bg-med/10 p-3 text-sm text-med-fg">
                    <Icon name="alert" size={18} />{data.analysis.summary.paths_truncated ? t('warn.truncated') : t('warn.partial')}
                  </p>
                )}
                <RecsList env={data.env} recs={data.recs} onSimulate={simulateAction} onActivity={refreshActivity} />
                </>}
              </div>
            )}
            {tab === 'evidence' && (
              <div className="mx-auto max-w-6xl space-y-4">
                <SubTabs value={evView} onChange={setEvView} items={[['evidence', t('sub.evidence')], ['assumptions', t('sub.assumptions')]]} label={t('nav.evidence')} />
                {evView === 'evidence' ? <EvidenceTab env={data.env} /> : <AssumptionsTab onConfigChanged={onEnvChanged} />}
              </div>
            )}
            {tab === 'environment' && <EnvTab env={data.env} meta={meta} onChanged={onEnvChanged} activity={activity} />}
          </>
        )}
      </main>
    </div>
    </ModeContext.Provider>
  )
}

function SubTabs<T extends string>({ value, onChange, items, label }: { value: T; onChange: (v: T) => void; items: [T, string][]; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="flex gap-1">
      {items.map(([k, text]) => (
        <button key={k} role="tab" aria-selected={value === k} onClick={() => onChange(k)} data-testid={`subtab-${k}`}
          className={`min-h-9 rounded-md px-3 text-sm font-medium max-sm:min-h-11 ${value === k ? 'bg-raised text-cloud ring-1 ring-hairline-2' : 'text-mist hover:text-cloud'}`}>{text}</button>
      ))}
    </div>
  )
}
