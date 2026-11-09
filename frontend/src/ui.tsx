import { useEffect, useId, useRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { Icon, type IconName } from './icons'
import { useI18n } from './i18n'
import type { Severity } from './types'

/* ------------------------------------------------------------------ severity */
// Full class names so Tailwind can see them. Fills use the base colour, text uses the lighter -fg tint (contrast).
export const SEV: Record<Severity, { fill: string; text: string; soft: string; bar: string }> = {
  critical: { fill: 'bg-crit', text: 'text-crit-fg', soft: 'border-crit/45 bg-crit/10', bar: 'bg-crit' },
  high: { fill: 'bg-high', text: 'text-high-fg', soft: 'border-high/45 bg-high/10', bar: 'bg-high' },
  medium: { fill: 'bg-med', text: 'text-med-fg', soft: 'border-med/45 bg-med/10', bar: 'bg-med' },
  low: { fill: 'bg-low', text: 'text-low-fg', soft: 'border-low/45 bg-low/10', bar: 'bg-low' },
}
export const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low']

export function SeverityBadge({ severity }: { severity: Severity }) {
  const { t } = useI18n()
  const s = SEV[severity]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-xs font-medium ${s.soft} ${s.text}`}>
      <span className={`size-1.5 rounded-full ${s.fill}`} aria-hidden />
      {t(`sev.${severity}`)}
    </span>
  )
}

const IMPACT: Record<string, { text: string; soft: string; fill: string }> = {
  none: { text: 'text-mist', soft: 'border-hairline-2 bg-raised', fill: 'bg-faint' },
  low: { text: SEV.low.text, soft: SEV.low.soft, fill: SEV.low.fill },
  medium: { text: SEV.medium.text, soft: SEV.medium.soft, fill: SEV.medium.fill },
  high: { text: SEV.critical.text, soft: SEV.critical.soft, fill: SEV.critical.fill },
}

/** Operational impact of a change (how much legitimate work it may disrupt). */
export function ImpactBadge({ level }: { level: string }) {
  const { t } = useI18n()
  const s = IMPACT[level] ?? IMPACT.none
  return (
    <span className={`inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-xs font-medium ${s.soft} ${s.text}`}>
      <span className={`size-1.5 rounded-full ${s.fill}`} aria-hidden />
      {t('impact.' + level)}
    </span>
  )
}

/* ------------------------------------------------------------------ evidence */
const EV_STYLE: Record<string, { cls: string; dash: string | undefined }> = {
  observed: { cls: 'border-teal/30 bg-teal/5 text-teal', dash: '10 3 2 3' },
  validated: { cls: 'border-teal/50 bg-teal/10 text-teal', dash: undefined },
  inferred: { cls: 'border-hairline-2 bg-lift text-mist', dash: '5 3' },
  theoretical: { cls: 'border-dashed border-hairline-2 text-faint', dash: '1.5 3.5' },
}

/**
 * Evidence level of a relationship or a whole path. The small line sample repeats the stroke pattern used on the
 * graph (solid / dashed / dotted) so the distinction never relies on colour alone.
 */
export function EvidenceTag({ level }: { level: string }) {
  const { t } = useI18n()
  const s = EV_STYLE[level] ?? EV_STYLE.theoretical
  return (
    <span title={`${t('ev.def.' + level)} ${t('ev.synthetic.note')}`} className={`inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-xs font-medium ${s.cls}`}>
      <svg width="16" height="6" viewBox="0 0 16 6" aria-hidden="true"><line x1="0" y1="3" x2="16" y2="3" stroke="currentColor" strokeWidth="2" strokeDasharray={s.dash} /></svg>
      {t(`cls.${level}`)}
    </span>
  )
}
export const ClassBadge = ({ cls }: { cls: string }) => <EvidenceTag level={cls} />

export function EvidenceLegend() {
  const { t } = useI18n()
  return (
    <details className="group rounded-md border border-hairline p-2.5 text-xs text-mist">
      <summary className="flex cursor-pointer list-none items-center gap-2 text-cloud">
        <Icon name="info" size={15} className="text-teal" />
        {t('ev.legend')}
        <Icon name="chevron" size={14} className="ms-auto transition-transform group-open:rotate-90" />
      </summary>
      <ul className="mt-2.5 space-y-1.5">
        {['validated', 'observed', 'inferred', 'theoretical'].map((l) => (
          <li key={l} className="flex flex-wrap items-center gap-2"><EvidenceTag level={l} /> <span>{t('ev.def.' + l)}</span></li>
        ))}
      </ul>
      <p className="mt-2.5 text-faint">{t('ev.synthetic.note')}</p>
    </details>
  )
}

/* ------------------------------------------------------------------ layout primitives */
export function Panel({ title, hint, action, children, className = '', flush = false, id }: {
  title?: ReactNode; hint?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; flush?: boolean; id?: string
}) {
  return (
    <section id={id} className={`rise rounded-lg border border-hairline bg-surface ${className}`}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 border-b border-hairline px-4 py-3">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold text-cloud">{title}</h2>}
            {hint && <p className="mt-0.5 text-xs text-faint">{hint}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={flush ? '' : 'p-4'}>{children}</div>
    </section>
  )
}
export const Card = Panel

export function Button({ variant = 'ghost', icon, className = '', children, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' | 'danger' | 'quiet'; icon?: IconName }) {
  const v = {
    primary: 'bg-teal text-teal-ink hover:bg-teal/90 disabled:bg-teal/30 disabled:text-teal-ink/70',
    ghost: 'border border-hairline-2 bg-raised text-cloud hover:bg-lift disabled:opacity-45',
    danger: 'border border-crit/55 bg-crit/10 text-crit-fg hover:bg-crit/20',
    quiet: 'text-mist hover:bg-raised hover:text-cloud disabled:opacity-45',
  }[variant]
  return (
    <button {...p} className={`inline-flex min-h-9 items-center justify-center gap-2 rounded-md px-3.5 text-sm font-medium transition-colors disabled:cursor-not-allowed max-sm:min-h-11 ${v} ${className}`}>
      {icon && <Icon name={icon} size={16} />}
      {children}
    </button>
  )
}

export function Spinner({ label }: { label: string }) {
  return (
    <div role="status" className="flex items-center gap-3 p-8 text-mist">
      <span className="size-4 animate-spin rounded-full border-2 border-teal border-t-transparent" aria-hidden />
      {label}
    </div>
  )
}

export function Empty({ children, icon = 'info', action }: { children: ReactNode; icon?: IconName; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-md border border-dashed border-hairline-2 p-4 text-sm text-mist sm:flex-row sm:items-center">
      <Icon name={icon} size={20} className="text-faint" />
      <p className="flex-1">{children}</p>
      {action}
    </div>
  )
}

/** Ids and other Latin tokens inside Arabic text: isolated so they never reorder the sentence around them. */
export function Id({ children }: { children: ReactNode }) {
  return <bdi dir="ltr" className="font-mono text-xs text-faint">{children}</bdi>
}

export function Pips({ n, max = 5 }: { n: number; max?: number }) {
  return (
    <span role="img" aria-label={`${n}/${max}`} className="inline-flex items-center gap-0.5">
      {Array.from({ length: max }, (_, i) => <span key={i} className={`h-2.5 w-1.5 rounded-[1px] ${i < n ? 'bg-teal' : 'bg-hairline-2'}`} />)}
    </span>
  )
}

/** Proportional bar from real counts. Zero-width segments are skipped. */
export function StackedBar({ segments, label, className = 'h-2.5' }: { segments: { value: number; className: string }[]; label: string; className?: string }) {
  const total = segments.reduce((a, s) => a + s.value, 0)
  return (
    <div role="img" aria-label={label} className={`flex w-full gap-px overflow-hidden rounded-sm bg-hairline ${className}`}>
      {total > 0 && (
        <div className="grow flex h-full w-full gap-px">
          {segments.filter((s) => s.value > 0).map((s, i) => <span key={i} className={`h-full ${s.className}`} style={{ flexGrow: s.value, flexBasis: 0 }} />)}
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ dialog & forms */
/** Native modal <dialog>: focus is trapped, Escape closes, and the page behind is inert. */
export function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const { t } = useI18n()
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  useEffect(() => {
    const d = ref.current
    const opener = document.activeElement as HTMLElement | null
    if (d && !d.open) d.showModal()
    return () => {
      if (d?.open) d.close()
      // React removes the node before this cleanup runs, so the browser's own focus restore never happens: do it here.
      if (opener?.isConnected) opener.focus()
    }
  }, [])
  return (
    <dialog ref={ref} aria-labelledby={titleId} onCancel={(e) => { e.preventDefault(); onClose() }} onClick={(e) => { if (e.target === ref.current) onClose() }}>
      <div className="flex items-center justify-between gap-3 border-b border-hairline px-5 py-3.5">
        <h2 id={titleId} className="text-base font-semibold">{title}</h2>
        <button type="button" onClick={onClose} aria-label={t('common.close')} className="grid size-9 place-items-center rounded-md text-mist hover:bg-raised hover:text-cloud max-sm:size-11">
          <Icon name="x" size={18} />
        </button>
      </div>
      <div className="overflow-y-auto p-5" style={{ maxHeight: 'calc(100dvh - 8rem)' }}>{children}</div>
    </dialog>
  )
}

export const controlCls = 'block w-full min-h-10 rounded-md border border-hairline-2 bg-abyss px-3 text-sm text-cloud placeholder:text-faint hover:border-faint max-sm:min-h-11 aria-[invalid=true]:border-crit'

export function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string; children: (a: { id: string; describedBy?: string; invalid: boolean }) => ReactNode }) {
  const id = useId()
  const descId = `${id}-d`
  return (
    <div className="block text-sm">
      <label htmlFor={id} className="mb-1.5 block font-medium text-mist">{label}</label>
      {children({ id, describedBy: error || hint ? descId : undefined, invalid: !!error })}
      {(error || hint) && <p id={descId} className={`mt-1 text-xs ${error ? 'text-crit-fg' : 'text-faint'}`}>{error ?? hint}</p>}
    </div>
  )
}

export function Check({ label, checked, onChange, disabled }: { label: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className="flex min-h-10 cursor-pointer items-center gap-2.5 text-sm max-sm:min-h-11">
      <input type="checkbox" className="size-4 accent-teal" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  )
}
