import { useState } from 'react'
import { api } from './api'
import { actionText, findRel } from './helpers'
import { useI18n } from './i18n'
import { Icon } from './icons'
import type { Environment, Explanation, RecExplanation, Recommendation, SimAction } from './types'
import { Button, Empty, EvidenceTag, ImpactBadge, StackedBar } from './ui'

interface Props {
  env: Environment
  recs: Recommendation[]
  onSimulate: (a: SimAction) => void
  onActivity: () => void
  limit?: number
  compact?: boolean
}

export default function RecsList({ env, recs, onSimulate, onActivity, limit, compact = false }: Props) {
  const { t, assetName, lang, num } = useI18n()
  const [open, setOpen] = useState<Record<string, Explanation>>({})
  const [nine, setNine] = useState<Record<string, RecExplanation>>({})
  const [err, setErr] = useState('')
  const list = limit ? recs.slice(0, limit) : recs

  const explain = async (id: string) => {
    setErr('')
    try {
      const e = await api.explain('recommendation', id, lang)
      setOpen((o) => ({ ...o, [id]: e }))
      const n = await api.recExplanation(id)
      setNine((o) => ({ ...o, [id]: n }))
      onActivity()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }

  if (list.length === 0) return <Empty icon="bulb">{t('rec.none')}</Empty>
  return (
    <>
      <ul data-testid="recommendations" className={compact ? 'grid gap-3 md:grid-cols-3' : 'space-y-4'}>
        {list.map((r, idx) => {
          const imp = r.operational_impact
          const rels = imp.affected_relationships.map((i) => findRel(env, i.relationship_id)).filter((x) => !!x)
          const evidence = [...new Set(rels.map((x) => x!.evidence))]
          const noUse = imp.affected_relationships.some((i) => !i.legitimate_use)
          const unchanged = Math.max(0, r.paths_remaining - r.paths_mitigated)
          const reversible = imp.fully_reversible
          return (
            <li key={r.id} className="rise flex flex-col rounded-lg border border-hairline bg-surface">
              <div className="flex items-start gap-3 border-b border-hairline p-4">
                <span className="tnum grid size-8 shrink-0 place-items-center rounded-md border border-hairline-2 bg-raised font-mono text-sm text-mist" title={t('rec.rank')}>{idx + 1}</span>
                <h3 className="min-w-0 flex-1 text-sm font-semibold leading-snug">{actionText(r.action, env, t, assetName)}</h3>
                <span className="shrink-0 rounded border border-teal/40 bg-teal/10 px-2 py-0.5 text-xs font-medium text-teal" title={t('rec.priority.help')}>{t('rec.priority')} {num(r.priority)}</span>
              </div>

              <div className={`grid flex-1 gap-x-6 gap-y-4 p-4 ${compact ? '' : 'md:grid-cols-3'}`}>
                <div>
                  <h4 className="text-xs font-semibold text-faint">{t('rec.why')}</h4>
                  <p className="mt-1.5 text-sm text-mist">{t('rec.why.text', { eliminated: r.paths_eliminated, mitigated: r.paths_mitigated, remaining: r.paths_remaining })}</p>
                  {!compact && (
                    <p className="mt-2 text-xs text-faint">{noUse ? t('rec.fact.nolegit') : t('rec.fact.legit')}</p>
                  )}
                </div>

                <div>
                  <h4 className="text-xs font-semibold text-faint">{t('rec.outcome')}</h4>
                  <div className="mt-2">
                    <StackedBar label={t('rec.outcome')} segments={[
                      { value: r.paths_eliminated, className: 'bg-teal' },
                      { value: r.paths_mitigated, className: 'bg-high' },
                      { value: unchanged, className: 'bg-hairline-2' },
                    ]} />
                  </div>
                  <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-mist">
                    <li className="flex items-center gap-1.5"><span className="size-2 rounded-sm bg-teal" aria-hidden />{t('rec.eliminated')} <b className="tnum text-cloud">{r.paths_eliminated}</b></li>
                    <li className="flex items-center gap-1.5"><span className="size-2 rounded-sm bg-high" aria-hidden />{t('rec.mitigated')} <b className="tnum text-cloud">{r.paths_mitigated}</b></li>
                    <li className="flex items-center gap-1.5"><span className="size-2 rounded-sm bg-hairline-2" aria-hidden />{t('rec.unchanged')} <b className="tnum text-cloud">{unchanged}</b></li>
                  </ul>
                </div>

                <div>
                  <h4 className="text-xs font-semibold text-faint">{t('rec.tradeoff')}</h4>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <ImpactBadge level={r.tradeoff} />
                    <span className={`inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-xs ${reversible ? 'border-teal/40 text-teal' : 'border-hairline-2 text-mist'}`}>
                      <Icon name={reversible ? 'undo' : 'lock'} size={12} />{reversible ? t('sim.reversible') : t('sim.irreversible')}
                    </span>
                  </div>
                  {imp.lost_access.length > 0 && <p className="mt-2 text-xs text-high-fg">{t('sim.impact.lost')}: {imp.lost_access.length}</p>}
                </div>
              </div>

              <div className="space-y-3 border-t border-hairline p-4">
                {!compact && evidence.length > 0 && (
                  <p className="flex flex-wrap items-center gap-2 text-xs text-mist"><span className="text-faint">{t('rec.evidence')}</span>{evidence.map((e) => <EvidenceTag key={e} level={e} />)}</p>
                )}
                <p className="flex items-start gap-2 text-xs text-faint"><Icon name="lock" size={14} className="mt-px" /><span><b className="font-medium text-mist">{t('rec.approval')}</b> {!compact && t('rec.approval.help')}</span></p>
                <div className="flex flex-wrap gap-2">
                  <Button variant="primary" icon="sliders" onClick={() => onSimulate(r.action)}>{t('rec.simulate')}</Button>
                  <Button icon="info" onClick={() => void explain(r.id)}>{t('rec.explain')}</Button>
                </div>
                {open[r.id] && (
                  <div className="space-y-2 border-t border-hairline pt-3 text-sm">
                    <p data-testid="rec-explanation">{open[r.id].template_explanation}</p>
                    {nine[r.id] && (
                      <section aria-label={t('rec.nine')} data-testid="rec-nine" className="rounded-md border border-hairline p-3">
                        <h4 className="flex flex-wrap items-center gap-2 text-xs font-semibold text-faint">{t('rec.nine')}
                          <span className="rounded border border-hairline-2 px-1.5 py-0.5 font-normal text-mist" data-testid="rec-confidence">{t('rec.confidence')}: {t(`conf.${nine[r.id].confidence.level}`)}</span>
                        </h4>
                        <dl className="mt-2 space-y-2.5">
                          {nine[r.id].questions.map((q) => (
                            <div key={q.key}><dt className="text-xs font-semibold text-mist">{q.question[lang]}</dt><dd className="mt-0.5 text-sm">{q.answer[lang]}</dd></div>
                          ))}
                        </dl>
                      </section>
                    )}
                    {open[r.id].ai_explanation && (
                      <p className="rounded-md border border-dashed border-hairline-2 p-2 text-mist"><b className="block text-xs">{t('ai.label')}</b>{open[r.id].ai_explanation}</p>
                    )}
                  </div>
                )}
              </div>
            </li>
          )
        })}
      </ul>
      {err && <p role="alert" className="mt-3 text-sm text-crit-fg">{err}</p>}
    </>
  )
}
