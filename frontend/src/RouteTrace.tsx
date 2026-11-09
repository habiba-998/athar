import { useI18n } from './i18n'
import { Icon } from './icons'
import { useNarrow } from './hooks'
import type { Severity } from './types'

/**
 * ATHAR's signature element: an attack path drawn as a trace.
 *  - the compromised start is a filled red dot, the sensitive target a diamond tinted by severity
 *  - each segment's stroke encodes the evidence behind that hop: solid = validated, dashed = inferred, dotted = theoretical
 *  - `cutAt` draws a severed segment (what a simulated defence removes)
 * It reads in the language's direction (mirrors in RTL) and stacks vertically on phones or when asked.
 */
const LINE: Record<Severity, string> = { critical: 'border-crit/70', high: 'border-high/70', medium: 'border-med/70', low: 'border-low/70' }
const DIAMOND: Record<Severity, string> = { critical: 'bg-crit', high: 'bg-high', medium: 'bg-med', low: 'bg-low' }
const STROKE: Record<string, string> = { validated: 'border-solid', inferred: 'border-dashed', theoretical: 'border-dotted' }

interface Props {
  names: string[]
  evidence: string[]
  severity?: Severity
  cutAt?: number
  vertical?: boolean
  compact?: boolean
}

function Ring({ role, severity }: { role: 'source' | 'mid' | 'target'; severity: Severity }) {
  if (role === 'source') return <span className="relative z-10 size-3.5 rounded-full border-2 border-crit bg-crit" />
  if (role === 'target') return <span className={`relative z-10 size-3 rotate-45 rounded-[2px] ${DIAMOND[severity]}`} />
  return <span className="relative z-10 size-3 rounded-full border-2 border-teal bg-abyss" />
}

export default function RouteTrace({ names, evidence, severity = 'critical', cutAt, vertical, compact }: Props) {
  const { t, arrow } = useI18n()
  const narrow = useNarrow()
  const stack = vertical ?? narrow
  const n = names.length
  const seg = (i: number) => `${STROKE[evidence[i]] ?? 'border-dotted'} ${LINE[severity]}`
  const role = (i: number): 'source' | 'mid' | 'target' => (i === 0 ? 'source' : i === n - 1 ? 'target' : 'mid')
  const aria = compact ? { 'aria-hidden': true as const } : { 'aria-label': names.join(` ${arrow} `) }

  if (stack) {
    return (
      <ol {...aria} className="m-0 list-none p-0">
        {names.map((name, i) => (
          <li key={i} className={`relative flex gap-3 ${i < n - 1 ? 'pb-4' : ''}`}>
            <div className="relative flex w-4 shrink-0 justify-center pt-1">
              <Ring role={role(i)} severity={severity} />
              {i < n - 1 && <span className={`absolute -bottom-0 start-1/2 top-3.5 border-s-2 ${seg(i)}`} style={{ marginInlineStart: -1 }} />}
              {cutAt === i && (
                <span className="absolute bottom-[-0.45rem] z-20 grid size-4 place-items-center rounded-full border border-crit bg-abyss text-crit-fg" title={t('trace.cut')}>
                  <Icon name="scissors" size={10} />
                </span>
              )}
            </div>
            <span className={`min-w-0 break-words text-sm leading-snug ${i === 0 || i === n - 1 ? 'font-medium text-cloud' : 'text-mist'}`}>{name}</span>
          </li>
        ))}
      </ol>
    )
  }

  return (
    <ol {...aria} className="m-0 grid list-none p-0" style={{ gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))` }}>
      {names.map((name, i) => (
        <li key={i} className={`relative flex min-w-0 flex-col items-center text-center ${compact ? 'gap-0' : 'gap-2'}`}>
          <div className="relative flex h-4 w-full items-center justify-center">
            {i > 0 && <span className={`absolute start-0 w-1/2 border-t-2 ${seg(i - 1)}`} />}
            {i < n - 1 && <span className={`absolute end-0 w-1/2 border-t-2 ${seg(i)}`} />}
            <Ring role={role(i)} severity={severity} />
            {cutAt === i && (
              <span className="absolute end-0 z-20 grid size-4 translate-x-1/2 place-items-center rounded-full border border-crit bg-abyss text-crit-fg rtl:-translate-x-1/2" title={t('trace.cut')}>
                <Icon name="scissors" size={10} />
              </span>
            )}
          </div>
          {!compact && <span className={`w-full break-words px-1 text-xs leading-tight ${i === 0 || i === n - 1 ? 'font-medium text-cloud' : 'text-mist'}`}>{name}</span>}
        </li>
      ))}
    </ol>
  )
}
