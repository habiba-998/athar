import { memo, useEffect, useMemo, useState } from 'react'
import { Background, BackgroundVariant, Controls, Handle, MarkerType, Position, ReactFlow, useReactFlow, useStore, type Edge, type EdgeChange, type Node, type NodeChange, type NodeProps } from '@xyflow/react'
import { useNarrow } from './hooks'
import { useI18n } from './i18n'
import { Icon, TYPE_ICON, type IconName } from './icons'
import { computeLayout } from './layout'
import { Pips } from './ui'
import type { AttackPath, Environment, SimResult } from './types'

export type Selection = { kind: 'asset' | 'rel'; id: string } | null

interface AssetData extends Record<string, unknown> {
  name: string
  typeLabel: string
  icon: IconName
  criticality: number
  compromised: boolean
  compromisedLabel: string
  onPath: boolean
  dim: boolean
  sensitive: boolean
  match: boolean
  sensitiveLabel: string
  src: Position
  tgt: Position
}

/** One asset on the graph: glyph, name, type and criticality. Colour is reserved for state (compromised / on path / selected). */
const AssetNode = memo(function AssetNode({ data, selected }: NodeProps) {
  const d = data as AssetData
  const ring = selected ? 'border-teal ring-2 ring-teal/60' : d.match ? 'border-cloud ring-2 ring-cloud/70' : d.compromised ? 'border-crit' : d.onPath ? 'border-teal/80' : 'border-hairline-2'
  const crown = d.sensitive ? 'border-s-[5px] border-s-high' : ''
  return (
    <div data-sensitive={d.sensitive || undefined} className={`w-[230px] rounded-lg border bg-surface px-3 py-2.5 text-start transition-opacity ${ring} ${crown} ${d.dim ? 'opacity-45' : ''}`}>
      <Handle type="target" position={d.tgt} isConnectable={false} />
      <Handle type="source" position={d.src} isConnectable={false} />
      <div className="flex items-start gap-2.5">
        <span className={`mt-0.5 grid size-7 shrink-0 place-items-center rounded-md border ${d.compromised ? 'border-crit/50 bg-crit/10 text-crit-fg' : 'border-hairline-2 bg-raised text-mist'}`}>
          <Icon name={d.icon} size={16} />
        </span>
        <div className="min-w-0 flex-1 leading-snug">
          <div className="text-[15px] font-semibold text-cloud">{d.name}</div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[13px] text-mist">
            <span>{d.typeLabel}</span>
            <Pips n={d.criticality} />
          </div>
          {d.compromised && <div className="mt-1 text-xs font-medium text-crit-fg">{d.compromisedLabel}</div>}
          {d.sensitive && !d.compromised && <div className="mt-1 text-xs font-medium text-high-fg">{d.sensitiveLabel}</div>}
        </div>
      </div>
    </div>
  )
})
const nodeTypes = { asset: AssetNode }

interface Props {
  env: Environment
  path: AttackPath | null
  sim: SimResult | null
  selection: Selection
  onSelect: (s: Selection) => void
  hiddenTypes?: Set<string>
  hiddenEvidence?: Set<string>
  query?: string
  onlyPath?: boolean
  height?: number
}

/** Selection arrives via change events so that keyboard (Enter/Space on a focused node) works as well as mouse clicks. */
function pickSelection(changes: (NodeChange | EdgeChange)[], kind: 'asset' | 'rel', current: Selection): { next: Selection } | null {
  let picked: string | null = null
  let cleared = false
  for (const c of changes) {
    if (c.type !== 'select') continue
    if (c.selected) picked = c.id
    else if (current?.kind === kind && current.id === c.id) cleared = true
  }
  if (picked) return { next: { kind, id: picked } }
  if (cleared) return { next: null }
  return null
}

/**
 * Frames the selected path. (ReactFlow's own `fitView` prop ignores its `nodes` option on first render and would show
 * the whole graph at a tiny zoom, so the bounding box is computed from our layout and fitted explicitly.)
 */
interface Bounds { x: number; y: number; width: number; height: number }
function FitToPath({ bounds }: { bounds: Bounds }) {
  const { fitBounds } = useReactFlow()
  const sized = useStore((s) => s.width > 0 && s.height > 0)   // the canvas must have a size before a fit means anything
  const { x, y, width, height } = bounds
  useEffect(() => {
    if (sized) void fitBounds({ x, y, width, height }, { padding: 0.15 })
  }, [sized, x, y, width, height, fitBounds])
  return null
}

// Evidence is encoded in the stroke pattern: solid = validated, dashed = inferred, dotted = theoretical.
const DASH: Record<string, string | undefined> = { validated: undefined, observed: '12 3 2 3', inferred: '8 5', theoretical: '2 6' }
const SENSITIVE_TYPES = new Set(['server', 'database', 'cloud', 'identity_provider'])

export default function GraphView({ env, path, sim, selection, onSelect, hiddenTypes, hiddenEvidence, query = '', onlyPath, height = 520 }: Props) {
  const { t, assetName, dir } = useI18n()
  const narrow = useNarrow()
  const [moved, setMoved] = useState<Record<string, { x: number; y: number }>>({})
  useEffect(() => setMoved({}), [env, dir, narrow])

  const { nodes, edges, bounds } = useMemo(() => {
    const pathNodes = new Set(path?.nodes ?? [])
    const pathRels = new Set(path?.relationship_ids ?? [])
    // Focus mode (phones, or "isolate path" anywhere): just the selected path as one vertical column, so labels stay legible.
    const focus = !!path && (narrow || !!onlyPath)
    const vertical = narrow || focus
    const pos = computeLayout(env, dir, vertical)
    if (focus && path) path.nodes.forEach((id, i) => { pos[id] = { x: 0, y: i * 130 } })
    // Handles sit where the flow enters/leaves: left-to-right (or mirrored in RTL), or top-to-bottom in vertical layouts.
    const src = vertical ? Position.Bottom : dir === 'rtl' ? Position.Left : Position.Right
    const tgt = vertical ? Position.Top : dir === 'rtl' ? Position.Right : Position.Left

    const blocked = new Set<string>()
    const mitigated = new Set<string>()
    for (const i of sim?.operational_impact.affected_relationships ?? []) {
      if (i.action === 'remove_relationship' || i.action === 'disable_relationship' || i.action === 'apply_segmentation') blocked.add(i.relationship_id)
      else mitigated.add(i.relationship_id)
    }
    const byId = new Map(env.assets.map((a) => [a.id, a]))
    const q = query.trim().toLowerCase()
    const matches = (a: { id: string; name: string; name_ar: string }) => q !== '' && `${a.id} ${a.name} ${a.name_ar}`.toLowerCase().includes(q)
    const visible = (id: string) => {
      const a = byId.get(id)
      if (!a || hiddenTypes?.has(a.type)) return false
      return !((onlyPath || focus) && path && !pathNodes.has(id))
    }

    const nodes: Node[] = env.assets.filter((a) => visible(a.id)).map((a) => {
      const on = pathNodes.has(a.id)
      return {
        id: a.id,
        type: 'asset',
        position: moved[a.id] ?? pos[a.id] ?? { x: 0, y: 0 },
        selected: selection?.kind === 'asset' && selection.id === a.id,
        ariaLabel: `${assetName(a)}, ${t(`type.${a.type}`)}, ${t('detail.criticality')} ${a.criticality}/5${a.compromised ? ', ' + t('graph.legend.compromised') : ''}`,
        data: {
          name: assetName(a), typeLabel: t(`type.${a.type}`), icon: TYPE_ICON[a.type] ?? 'server', criticality: a.criticality,
          compromised: a.compromised, compromisedLabel: t('graph.legend.compromised'), onPath: on, dim: (!!path && !on) || (q !== '' && !matches(a)), src, tgt,
          sensitive: a.criticality >= 4 && SENSITIVE_TYPES.has(a.type), match: matches(a), sensitiveLabel: t('graph.legend.sensitive'),
        } satisfies AssetData,
      }
    })

    const edges: Edge[] = env.relationships.filter((r) => visible(r.source) && visible(r.target) && !hiddenEvidence?.has(r.evidence)).map((r) => {
      const on = pathRels.has(r.id)
      const isBlocked = blocked.has(r.id)
      const isMit = mitigated.has(r.id)
      const sel = selection?.kind === 'rel' && selection.id === r.id
      const color = isBlocked ? '#ef5b6b' : isMit ? '#f2a03d' : on || sel ? '#34d1bf' : r.disabled ? '#5b6b88' : r.type === 'protects' ? '#4a5a78' : '#6f84ab'
      const label = isBlocked ? t('graph.edge.blocked') : isMit ? t('graph.edge.mitigated') : on || sel ? t(`rel.${r.type}`) : r.disabled ? t('rel.status.disabled') : undefined
      return {
        id: r.id,
        type: 'smoothstep',
        source: r.source,
        target: r.target,
        selected: sel,
        animated: false,
        ariaLabel: `${assetName(byId.get(r.source))} ${t(`rel.${r.type}`)} ${assetName(byId.get(r.target))}, ${t(`cls.${r.evidence}`)}${r.disabled ? ', ' + t('rel.status.disabled') : ''}`,
        label,
        labelStyle: { fill: '#e8eef9', fontSize: 12, fontWeight: 500 },
        labelBgStyle: { fill: '#060a14' },
        labelBgPadding: [6, 3],
        labelBgBorderRadius: 4,
        markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
        interactionWidth: 24,
        style: {
          stroke: color,
          strokeWidth: on || sel || isBlocked ? 2.75 : 1.5,
          strokeDasharray: r.type === 'protects' ? '3 4' : DASH[r.evidence],
          opacity: path && !on && !isBlocked && !isMit ? 0.28 : r.disabled ? 0.6 : 1,
        },
      }
    })
    // Bounding box of the selected path in layout coordinates (cards are about 230 x 72), used to frame it.
    let bounds: Bounds | null = null
    if (path) {
      const pts = path.nodes.map((id) => pos[id]).filter(Boolean)
      if (pts.length) {
        const x0 = Math.min(...pts.map((p) => p.x)), x1 = Math.max(...pts.map((p) => p.x)) + 230
        const y0 = Math.min(...pts.map((p) => p.y)), y1 = Math.max(...pts.map((p) => p.y)) + 72
        bounds = { x: x0, y: y0, width: x1 - x0, height: y1 - y0 }
      }
    }
    return { nodes, edges, bounds }
  }, [env, path, sim, selection, hiddenTypes, hiddenEvidence, query, onlyPath, dir, narrow, t, assetName, moved])

  // React Flow's built-in screen-reader text is English by default; localise all of it.
  const ariaLabelConfig = useMemo(() => ({
    'node.a11yDescription.default': t('graph.a11y.node'),
    'node.a11yDescription.keyboardDisabled': t('graph.a11y.nodeMove'),
    'node.a11yDescription.ariaLiveMessage': ({ direction, x, y }: { direction: string; x: number; y: number }) =>
      t('graph.a11y.moved', { direction: t(`graph.dir.${direction}`), x: Math.round(x), y: Math.round(y) }),
    'edge.a11yDescription.default': t('graph.a11y.edge'),
    'controls.ariaLabel': t('graph.ctl.panel'),
    'controls.zoomIn.ariaLabel': t('graph.ctl.zoomIn'),
    'controls.zoomOut.ariaLabel': t('graph.ctl.zoomOut'),
    'controls.fitView.ariaLabel': t('graph.ctl.fit'),
  }), [t])

  return (
    <div style={{ height, direction: 'ltr' }} className="overflow-hidden rounded-lg border border-hairline bg-abyss" data-testid="attack-graph" role="group" aria-label={t('dash.graph')}>
      <ReactFlow
        // re-mounting on language/layout/path change re-runs fitView so the visible content is always framed
        key={`${dir}-${narrow}-${path?.id ?? 'all'}-${!!onlyPath}`}
        ariaLabelConfig={ariaLabelConfig}
        deleteKeyCode={null}
        nodeTypes={nodeTypes}
        nodes={nodes}
        edges={edges}
        fitView={!path}
        fitViewOptions={{ padding: 0.14 }}
        minZoom={0.2}
        maxZoom={1.8}
        nodesConnectable={false}
        zoomOnScroll={false}      /* the page must stay scrollable with the pointer over the graph; zoom via controls, pinch or double-click */
        preventScrolling={false}
        onNodesChange={(changes) => {
          for (const c of changes) if (c.type === 'position' && c.position) setMoved((m) => ({ ...m, [c.id]: c.position! }))
          const s = pickSelection(changes, 'asset', selection)
          if (s) onSelect(s.next)
        }}
        onEdgesChange={(changes) => {
          const s = pickSelection(changes, 'rel', selection)
          if (s) onSelect(s.next)
        }}
        onPaneClick={() => onSelect(null)}
        colorMode="dark"
      >
        <Background variant={BackgroundVariant.Dots} color="#1b2a45" gap={22} size={1.4} />
        <Controls showInteractive={false} />
        {bounds && <FitToPath bounds={bounds} />}
      </ReactFlow>
    </div>
  )
}
