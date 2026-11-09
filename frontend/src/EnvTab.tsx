import { useMemo, useRef, useState, type ReactNode } from 'react'
import { api, ApiError } from './api'
import { findAsset } from './helpers'
import { useI18n } from './i18n'
import { Icon, TYPE_ICON } from './icons'
import { AuditPanel, ScenariosPanel, ServicesPanel } from './EnvExtras'
import { useMode } from './mode'
import type { Activity, Asset, EnvMeta, Environment, Relationship } from './types'
import { Button, Check, Dialog, EvidenceTag, Field, Id, Panel, Pips, controlCls } from './ui'

const ASSET_TYPES = ['user', 'service_account', 'group', 'server', 'database', 'cloud', 'identity_provider', 'control']
const REL_TYPES = ['member_of', 'can_login', 'admin_access', 'read_access', 'write_access', 'trusts', 'has_credentials', 'network_access', 'assumes_role', 'protects']
const MAX_IMPORT_BYTES = 1_048_576
const ID_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/

const blankAsset = (): Asset => ({ id: '', name: '', name_ar: '', type: 'server', criticality: 1, exposure: 'internal', compromised: false, description: '', description_ar: '', controls: [] })
const blankRel = (): Relationship => ({ id: '', source: '', target: '', type: 'read_access', privilege: 'none', evidence: 'inferred', legitimate_use: null, legitimate_use_ar: null, business_critical: false, mfa_required: false, disabled: false })

interface Props {
  env: Environment
  meta: EnvMeta | null
  onChanged: () => Promise<void>
  activity?: Activity[]
}

type Notice = { kind: 'ok' | 'error'; text: string; title?: string } | null
type Confirm = { kind: 'asset' | 'rel'; id: string; label: string; relCount: number } | null

export default function EnvTab({ env, meta, onChanged, activity = [] }: Props) {
  const { readOnly } = useMode()
  const { t, assetName, lang, arrow } = useI18n()
  const [notice, setNotice] = useState<Notice>(null)
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState<'assets' | 'relationships' | 'services' | 'scenarios' | 'audit'>('assets')
  const [query, setQuery] = useState('')
  const [assetForm, setAssetForm] = useState<{ value: Asset; isNew: boolean } | null>(null)
  const [relForm, setRelForm] = useState<{ value: Relationship; isNew: boolean } | null>(null)
  const [confirm, setConfirm] = useState<Confirm>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  /** Runs a mutation. Returns null on success or the error text. `inline` errors are shown by the calling form. */
  const run = async (fn: () => Promise<unknown>, okText: string, inline = false, title?: string): Promise<string | null> => {
    setBusy(true)
    setNotice(null)
    try {
      await fn()
      await onChanged()
      setNotice({ kind: 'ok', text: okText })
      return null
    } catch (e) {
      const text = e instanceof ApiError || e instanceof Error ? e.message : String(e)
      if (!inline) setNotice({ kind: 'error', text, title })
      return text
    } finally {
      setBusy(false)
    }
  }

  const onFile = async (file: File | undefined) => {
    if (!file) return
    if (file.size > MAX_IMPORT_BYTES) return setNotice({ kind: 'error', text: t('env.import.toolarge') })
    let parsed: unknown
    try {
      parsed = JSON.parse(await file.text())
    } catch {
      return setNotice({ kind: 'error', text: t('env.import.notjson') })
    }
    await run(() => api.importEnv(parsed), t('env.import.ok'), false, t('env.import.errors'))
  }

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(env, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'athar-environment.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  const q = query.trim().toLowerCase()
  const assets = useMemo(() => env.assets.filter((a) => !q || `${a.id} ${a.name} ${a.name_ar} ${a.type}`.toLowerCase().includes(q)), [env.assets, q])
  const rels = useMemo(
    () => env.relationships.filter((r) => {
      if (!q) return true
      const s = findAsset(env, r.source), g = findAsset(env, r.target)
      return `${r.id} ${r.type} ${r.evidence} ${s?.name ?? ''} ${s?.name_ar ?? ''} ${g?.name ?? ''} ${g?.name_ar ?? ''}`.toLowerCase().includes(q)
    }),
    [env, q],
  )
  const relLabel = (r: Relationship) => `${assetName(findAsset(env, r.source))} ${t(`rel.${r.type}`)} ${assetName(findAsset(env, r.target))}`

  const confirmDelete = async () => {
    const c = confirm
    if (!c) return
    setConfirm(null)
    await run(() => (c.kind === 'asset' ? api.deleteAsset(c.id) : api.deleteRel(c.id)), t('env.deleted'))
  }

  return (
    <div className="space-y-4">
      <Panel title={t('env.title')} hint={t('env.intro')}>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="inline-flex items-center gap-1.5 rounded border border-teal/45 bg-teal/10 px-2 py-0.5 text-xs font-medium text-teal"><Icon name="shield" size={13} />{t('chip.synthetic')}</span>
          <span className="rounded border border-hairline-2 bg-raised px-2 py-0.5 text-xs" data-testid="env-kind">{meta?.is_sample ? t('env.kind.sample') : t('env.kind.custom')}</span>
          <span className="text-mist" data-testid="env-name">{(lang === 'ar' && env.name_ar) || env.name}</span>
          <span className="tnum text-faint">· {env.assets.length} {t('env.assets')} · {env.relationships.length} {t('env.relationships')}</span>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button variant="primary" icon="upload" onClick={() => fileRef.current?.click()} disabled={busy || readOnly}>{t('env.import')}</Button>
          <input ref={fileRef} type="file" accept="application/json,.json" className="sr-only" aria-label={t('env.import')} data-testid="import-input" tabIndex={-1}
            onChange={(e) => { void onFile(e.target.files?.[0]); e.target.value = '' }} />
          <Button icon="download" onClick={exportJson}>{t('env.export')}</Button>
          <span className="mx-1 hidden h-6 w-px bg-hairline sm:block" aria-hidden />
          <Button icon="undo" disabled={busy || readOnly || !meta?.can_undo} onClick={() => void run(() => api.undoEnv(), t('env.undo.ok'))}>{t('env.undo')}</Button>
          <Button variant="quiet" disabled={busy || readOnly} onClick={() => void run(() => api.resetEnv(), t('env.reset.ok'))}>{t('env.reset')}</Button>
        </div>

        {readOnly && <p className="mt-3 rounded-md border border-hairline-2 bg-raised/50 p-2.5 text-sm text-mist" data-testid="env-readonly">{t('demo.readonly.note')}</p>}

        <details className="group mt-4 rounded-md border border-hairline text-sm">
          <summary className="flex min-h-10 cursor-pointer list-none items-center gap-2 px-3 text-mist hover:text-cloud">
            <Icon name="info" size={15} className="text-teal" />{t('env.format.title')}
            <Icon name="chevron" size={14} className="ms-auto transition-transform group-open:rotate-90" />
          </summary>
          <div className="space-y-1.5 border-t border-hairline px-3 py-3 text-xs text-mist">
            <p>{t('env.import.help')}</p>
            <p>{t('env.format.rules')}</p>
          </div>
        </details>

        {notice && (
          <div role={notice.kind === 'error' ? 'alert' : 'status'} data-testid="env-notice"
            className={`mt-4 max-h-56 overflow-y-auto whitespace-pre-line rounded-lg border p-3 text-sm ${notice.kind === 'error' ? 'border-crit/50 bg-crit/10 text-crit-fg' : 'border-teal/40 bg-teal/10 text-teal'}`}>
            {notice.title && <b className="mb-1 block">{notice.title}</b>}
            {notice.text}
          </div>
        )}
      </Panel>

      <Panel flush>
        <div className="flex flex-wrap items-center gap-3 border-b border-hairline px-3 py-2.5">
          <div role="tablist" aria-label={t('env.title')} className="flex min-w-0 max-w-full flex-wrap gap-1">
            {(['assets', 'relationships', 'services', 'scenarios', 'audit'] as const).map((k) => (
              <button key={k} role="tab" id={`tab-${k}`} aria-selected={tab === k} aria-controls={`panel-${k}`} onClick={() => setTab(k)}
                className={`min-h-9 rounded-md px-3 text-sm font-medium max-sm:min-h-11 ${tab === k ? 'bg-raised text-cloud ring-1 ring-hairline-2' : 'text-mist hover:text-cloud'}`}>
                {t(`env.${k}`)} {(k === 'assets' || k === 'relationships') && <span className="tnum text-faint">{k === 'assets' ? env.assets.length : env.relationships.length}</span>}
              </button>
            ))}
          </div>
          {(tab === 'assets' || tab === 'relationships') && <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('env.search')} aria-label={t('env.search')} className={`${controlCls} !w-auto min-w-0 flex-1 sm:max-w-xs sm:flex-none`} />}
          {(tab === 'assets' || tab === 'relationships') && <div className="ms-auto">
            {readOnly ? null : tab === 'assets'
              ? <Button icon="plus" onClick={() => setAssetForm({ value: blankAsset(), isNew: true })}>{t('env.add.asset')}</Button>
              : <Button icon="plus" onClick={() => setRelForm({ value: { ...blankRel(), source: env.assets[0]?.id ?? '', target: env.assets[1]?.id ?? '' }, isNew: true })}>{t('env.add.relationship')}</Button>}
          </div>}
        </div>

        {tab === 'services' ? <div role="tabpanel" id="panel-services" aria-labelledby="tab-services"><ServicesPanel env={env} /></div>
        : tab === 'scenarios' ? <div role="tabpanel" id="panel-scenarios" aria-labelledby="tab-scenarios"><ScenariosPanel env={env} onChanged={onChanged} /></div>
        : tab === 'audit' ? <div role="tabpanel" id="panel-audit" aria-labelledby="tab-audit"><AuditPanel activity={activity} /></div>
        : tab === 'assets' ? (
          <div role="tabpanel" id="panel-assets" aria-labelledby="tab-assets">
            <Table testId="asset-table" empty={assets.length === 0 ? t('env.noMatches') : ''} head={[t('tbl.name'), t('tbl.type'), t('field.criticality'), t('field.exposure'), t('tbl.actions')]}>
              {assets.map((a) => {
                const relCount = env.relationships.filter((r) => r.source === a.id || r.target === a.id).length
                return (
                  <tr key={a.id} className="border-t border-hairline align-middle hover:bg-raised/40">
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-2 font-medium">{assetName(a)}{a.compromised && <span className="rounded border border-crit/45 bg-crit/10 px-1.5 text-xs font-normal text-crit-fg">{t('graph.legend.compromised')}</span>}</div>
                      <Id>{a.id}</Id>
                    </td>
                    <td className="px-3"><span className="inline-flex items-center gap-1.5 text-mist"><Icon name={TYPE_ICON[a.type] ?? 'server'} size={15} />{t(`type.${a.type}`)}</span></td>
                    <td className="px-3"><Pips n={a.criticality} /></td>
                    <td className="px-3 text-mist">{t(`exp.${a.exposure}`)}</td>
                    <td className="px-3 py-2">
                      <div className={`flex flex-wrap gap-1 ${readOnly ? 'hidden' : ''}`}>
                        <Button variant="quiet" icon="edit" aria-label={`${t('env.edit')}: ${assetName(a)}`} onClick={() => setAssetForm({ value: { ...a }, isNew: false })}>{t('env.edit')}</Button>
                        <Button variant="quiet" icon="trash" aria-label={`${t('env.delete')}: ${assetName(a)}`} onClick={() => setConfirm({ kind: 'asset', id: a.id, label: assetName(a), relCount })}>{t('env.delete')}</Button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </Table>
          </div>
        ) : (
          <div role="tabpanel" id="panel-relationships" aria-labelledby="tab-relationships">
            <Table testId="rel-table" empty={rels.length === 0 ? t('env.noMatches') : ''} head={[t('tbl.relationship'), t('field.privilege'), t('field.evidence'), t('tbl.status'), t('tbl.actions')]}>
              {rels.map((r) => {
                const label = relLabel(r)
                return (
                  <tr key={r.id} className={`border-t border-hairline align-middle hover:bg-raised/40 ${r.disabled ? 'opacity-70' : ''}`}>
                    <td className="px-3 py-2.5">
                      <div>{assetName(findAsset(env, r.source))} <span className="text-faint">{arrow}</span> <span className="text-mist">{t(`rel.${r.type}`)}</span> <span className="text-faint">{arrow}</span> {assetName(findAsset(env, r.target))}</div>
                      <Id>{r.id}</Id>
                    </td>
                    <td className="px-3 text-mist">{t(`priv.${r.privilege}`)}</td>
                    <td className="px-3"><EvidenceTag level={r.evidence} /></td>
                    <td className="px-3"><span className={`rounded border px-1.5 py-0.5 text-xs ${r.disabled ? 'border-hairline-2 text-faint' : 'border-low/40 text-low-fg'}`}>{r.disabled ? t('rel.status.disabled') : t('rel.status.active')}</span></td>
                    <td className="px-3 py-2">
                      <div className={`flex flex-wrap gap-1 ${readOnly ? 'hidden' : ''}`}>
                        <Button variant="quiet" icon="edit" aria-label={`${t('env.edit')}: ${label}`} onClick={() => setRelForm({ value: { ...r }, isNew: false })}>{t('env.edit')}</Button>
                        {r.type !== 'protects' && (
                          <Button variant="quiet" disabled={busy} aria-label={`${r.disabled ? t('rel.enable') : t('rel.disable')}: ${label}`}
                            onClick={() => void run(() => api.updateRel({ ...r, disabled: !r.disabled }), t('env.saved'))}>{r.disabled ? t('rel.enable') : t('rel.disable')}</Button>
                        )}
                        <Button variant="quiet" icon="trash" aria-label={`${t('env.delete')}: ${label}`} onClick={() => setConfirm({ kind: 'rel', id: r.id, label, relCount: 0 })}>{t('env.delete')}</Button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </Table>
          </div>
        )}
      </Panel>

      {assetForm && (
        <AssetDialog form={assetForm} controls={env.assets.filter((a) => a.type === 'control')} onCancel={() => setAssetForm(null)}
          onSubmit={async (v) => { const err = await run(() => (assetForm.isNew ? api.createAsset(v) : api.updateAsset(v)), t('env.saved'), true); if (!err) setAssetForm(null); return err }} />
      )}
      {relForm && (
        <RelDialog form={relForm} assets={env.assets} onCancel={() => setRelForm(null)}
          onSubmit={async (v) => { const err = await run(() => (relForm.isNew ? api.createRel(v) : api.updateRel(v)), t('env.saved'), true); if (!err) setRelForm(null); return err }} />
      )}
      {confirm && (
        <Dialog title={confirm.kind === 'asset' ? t('env.confirm.asset') : t('env.confirm.rel')} onClose={() => setConfirm(null)}>
          <p className="text-sm font-medium">{confirm.label}</p>
          <p className="mt-2 text-sm text-mist">{t('env.confirm.body')}</p>
          {confirm.kind === 'asset' && confirm.relCount > 0 && <p className="mt-2 rounded-md border border-high/40 bg-high/10 p-2.5 text-sm text-high-fg">{t('env.confirmDelete.rels', { n: confirm.relCount })}</p>}
          <div className="mt-5 flex flex-wrap justify-end gap-2">
            <Button variant="ghost" onClick={() => setConfirm(null)}>{t('env.cancel')}</Button>
            <Button variant="danger" icon="trash" disabled={busy} aria-label={`${t('env.confirmDelete')}: ${confirm.label}`} onClick={() => void confirmDelete()}>{t('env.confirmDelete')}</Button>
          </div>
        </Dialog>
      )}
    </div>
  )
}

function Table({ head, children, testId, empty }: { head: string[]; children: ReactNode; testId: string; empty: string }) {
  return (
    <div className="overflow-x-auto" data-testid={testId}>
      <table className="w-full min-w-[620px] text-sm">
        <thead>
          <tr className="text-xs text-faint">{head.map((h) => <th key={h} scope="col" className="px-3 py-2 text-start font-medium">{h}</th>)}</tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
      {empty && <p className="border-t border-hairline p-4 text-sm text-faint">{empty}</p>}
    </div>
  )
}

/** Server-side messages are shown verbatim as a list, one problem per line. */
function FormErrors({ text }: { text: string }) {
  const { t } = useI18n()
  if (!text) return null
  return (
    <div role="alert" className="rounded-lg border border-crit/50 bg-crit/10 p-3 text-sm text-crit-fg">
      <b className="block">{t('env.form.error')}</b>
      <ul className="mt-1 list-disc ps-5">{text.split('\n').map((l, i) => <li key={i}>{l}</li>)}</ul>
    </div>
  )
}

function FormActions({ busy, onCancel }: { busy: boolean; onCancel: () => void }) {
  const { t } = useI18n()
  return (
    <div className="flex flex-wrap justify-end gap-2 pt-1">
      <Button type="button" variant="ghost" onClick={onCancel}>{t('env.cancel')}</Button>
      <Button type="submit" variant="primary" disabled={busy}>{t('env.save')}</Button>
    </div>
  )
}

function AssetDialog({ form, controls, onSubmit, onCancel }: { form: { value: Asset; isNew: boolean }; controls: Asset[]; onSubmit: (v: Asset) => Promise<string | null>; onCancel: () => void }) {
  const { t, assetName } = useI18n()
  const [v, setV] = useState<Asset>(form.value)
  const [errs, setErrs] = useState<Record<string, string>>({})
  const [serverErr, setServerErr] = useState('')
  const [busy, setBusy] = useState(false)
  const set = <K extends keyof Asset>(k: K, val: Asset[K]) => setV((p) => ({ ...p, [k]: val }))

  const submit = async () => {
    const e: Record<string, string> = {}
    if (!ID_RE.test(v.id)) e.id = t('field.err.id')
    if (!v.name.trim()) e.name = t('field.err.required')
    if (!v.name_ar.trim()) e.name_ar = t('field.err.required')
    if (!(v.criticality >= 1 && v.criticality <= 5)) e.criticality = t('field.err.range')
    setErrs(e)
    if (Object.keys(e).length) return
    setBusy(true)
    setServerErr((await onSubmit({ ...v, criticality: Number(v.criticality) })) ?? '')
    setBusy(false)
  }

  return (
    <Dialog title={form.isNew ? t('env.add.asset') : t('env.edit')} onClose={onCancel}>
      <form noValidate aria-label={form.isNew ? t('env.add.asset') : t('env.edit')} className="space-y-4" onSubmit={(ev) => { ev.preventDefault(); void submit() }}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t('field.id')} error={errs.id}>{({ id, describedBy, invalid }) => <input id={id} aria-describedby={describedBy} aria-invalid={invalid} className={`${controlCls} font-mono`} dir="ltr" value={v.id} disabled={!form.isNew} onChange={(e) => set('id', e.target.value)} />}</Field>
          <Field label={t('field.type')}>{({ id }) => <select id={id} className={controlCls} value={v.type} onChange={(e) => set('type', e.target.value)}>{ASSET_TYPES.map((x) => <option key={x} value={x}>{t(`type.${x}`)}</option>)}</select>}</Field>
          <Field label={t('field.name')} error={errs.name}>{({ id, describedBy, invalid }) => <input id={id} aria-describedby={describedBy} aria-invalid={invalid} className={controlCls} maxLength={200} value={v.name} onChange={(e) => set('name', e.target.value)} />}</Field>
          <Field label={t('field.nameAr')} error={errs.name_ar}>{({ id, describedBy, invalid }) => <input id={id} aria-describedby={describedBy} aria-invalid={invalid} className={controlCls} dir="rtl" lang="ar" maxLength={200} value={v.name_ar} onChange={(e) => set('name_ar', e.target.value)} />}</Field>
          <Field label={t('field.criticality')} error={errs.criticality} hint={t('field.criticality.hint')}>{({ id, describedBy, invalid }) => <input id={id} aria-describedby={describedBy} aria-invalid={invalid} className={controlCls} type="number" min={1} max={5} value={v.criticality} onChange={(e) => set('criticality', Number(e.target.value))} />}</Field>
          <Field label={t('field.exposure')}>{({ id }) => <select id={id} className={controlCls} value={v.exposure} onChange={(e) => set('exposure', e.target.value)}>{['internet', 'internal', 'restricted'].map((x) => <option key={x} value={x}>{t(`exp.${x}`)}</option>)}</select>}</Field>
          <Field label={t('field.description')}>{({ id }) => <input id={id} className={controlCls} maxLength={200} value={v.description} onChange={(e) => set('description', e.target.value)} />}</Field>
          <Field label={t('field.descriptionAr')}>{({ id }) => <input id={id} className={controlCls} dir="rtl" lang="ar" maxLength={200} value={v.description_ar} onChange={(e) => set('description_ar', e.target.value)} />}</Field>
        </div>
        {controls.length > 0 && (
          <fieldset className="rounded-md border border-hairline p-3">
            <legend className="px-1 text-sm font-medium text-mist">{t('field.controls')}</legend>
            <div className="grid gap-x-4 sm:grid-cols-2">
              {controls.map((c) => (
                <Check key={c.id} label={assetName(c)} checked={v.controls.includes(c.id)}
                  onChange={(on) => set('controls', on ? [...v.controls, c.id] : v.controls.filter((x) => x !== c.id))} />
              ))}
            </div>
          </fieldset>
        )}
        <Check label={t('field.compromised')} checked={v.compromised} onChange={(c) => set('compromised', c)} />
        <FormErrors text={serverErr} />
        <FormActions busy={busy} onCancel={onCancel} />
      </form>
    </Dialog>
  )
}

function RelDialog({ form, assets, onSubmit, onCancel }: { form: { value: Relationship; isNew: boolean }; assets: Asset[]; onSubmit: (v: Relationship) => Promise<string | null>; onCancel: () => void }) {
  const { t, assetName } = useI18n()
  const [v, setV] = useState<Relationship>(form.value)
  const [errs, setErrs] = useState<Record<string, string>>({})
  const [serverErr, setServerErr] = useState('')
  const [busy, setBusy] = useState(false)
  const set = <K extends keyof Relationship>(k: K, val: Relationship[K]) => setV((p) => ({ ...p, [k]: val }))
  const opts = assets.map((a) => <option key={a.id} value={a.id}>{assetName(a)}</option>)

  const submit = async () => {
    const e: Record<string, string> = {}
    if (!ID_RE.test(v.id)) e.id = t('field.err.id')
    setErrs(e)
    if (Object.keys(e).length) return
    setBusy(true)
    setServerErr((await onSubmit({ ...v, legitimate_use: v.legitimate_use || null, legitimate_use_ar: v.legitimate_use_ar || null })) ?? '')
    setBusy(false)
  }

  return (
    <Dialog title={form.isNew ? t('env.add.relationship') : t('env.edit')} onClose={onCancel}>
      <form noValidate aria-label={form.isNew ? t('env.add.relationship') : t('env.edit')} className="space-y-4" onSubmit={(ev) => { ev.preventDefault(); void submit() }}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t('field.id')} error={errs.id}>{({ id, describedBy, invalid }) => <input id={id} aria-describedby={describedBy} aria-invalid={invalid} className={`${controlCls} font-mono`} dir="ltr" value={v.id} disabled={!form.isNew} onChange={(e) => set('id', e.target.value)} />}</Field>
          <Field label={t('field.relType')}>{({ id }) => <select id={id} className={controlCls} value={v.type} onChange={(e) => set('type', e.target.value)}>{REL_TYPES.map((x) => <option key={x} value={x}>{t(`rel.${x}`)}</option>)}</select>}</Field>
          <Field label={t('field.source')}>{({ id }) => <select id={id} className={controlCls} value={v.source} onChange={(e) => set('source', e.target.value)}>{opts}</select>}</Field>
          <Field label={t('field.target')}>{({ id }) => <select id={id} className={controlCls} value={v.target} onChange={(e) => set('target', e.target.value)}>{opts}</select>}</Field>
          <Field label={t('field.privilege')}>{({ id }) => <select id={id} className={controlCls} value={v.privilege} onChange={(e) => set('privilege', e.target.value)}>{['none', 'read', 'write', 'admin'].map((x) => <option key={x} value={x}>{t(`priv.${x}`)}</option>)}</select>}</Field>
          <Field label={t('field.evidence')} hint={t('field.evidence.hint')}>{({ id, describedBy }) => <select id={id} aria-describedby={describedBy} className={controlCls} value={v.evidence} onChange={(e) => set('evidence', e.target.value)}>{['validated', 'observed', 'inferred', 'theoretical'].map((x) => <option key={x} value={x}>{t(`cls.${x}`)}</option>)}</select>}</Field>
          <Field label={t('field.legit')}>{({ id }) => <input id={id} className={controlCls} maxLength={200} value={v.legitimate_use ?? ''} onChange={(e) => set('legitimate_use', e.target.value)} />}</Field>
          <Field label={t('field.legitAr')}>{({ id }) => <input id={id} className={controlCls} dir="rtl" lang="ar" maxLength={200} value={v.legitimate_use_ar ?? ''} onChange={(e) => set('legitimate_use_ar', e.target.value)} />}</Field>
        </div>
        <div className="grid gap-x-4 sm:grid-cols-3">
          <Check label={t('field.bizcritical')} checked={v.business_critical} onChange={(c) => set('business_critical', c)} />
          <Check label={t('field.mfa')} checked={v.mfa_required} onChange={(c) => set('mfa_required', c)} />
          <Check label={t('field.disabled')} checked={v.disabled} onChange={(c) => set('disabled', c)} />
        </div>
        <FormErrors text={serverErr} />
        <FormActions busy={busy} onCancel={onCancel} />
      </form>
    </Dialog>
  )
}
