import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from 'd3-force'
import { AnimatePresence, motion } from 'framer-motion'
import { useLab } from '../lib/lab'

const W = 900
const H = 520

const PRIORITY_DOT = {
  0: { fill: '#c13a30', r: 7, glow: '#f2b3ad' },
  1: { fill: '#8a6444', r: 5, glow: '#ddc8b6' },
  2: { fill: '#c4a58b', r: 4, glow: '#efe4da' },
}

const ROLE_STROKE = { NORMAL: '#8a6444', GATEWAY: '#a62b23', RESCUE: '#6e1a16' }

/**
 * The live mesh. Nodes sit where a force simulation settles them (seeded from
 * the preset's layout so familiar shapes stay familiar); edges thicken with
 * measured link quality; a switched-off node greys out; packets are drawn
 * travelling hop by hop as the engine logs `sent` / `forward` events.
 *
 * `highlight` is a list of { path: [ids], tone } drawn over the links.
 */
export default function MeshGraph({
  snapshot,
  selected,
  onSelect,
  highlight = [],
  height = 460,
  showLoss = true,
  animate = true,
  dimOffline = true,
  onLinkClick,
}) {
  const { subscribe } = useLab()
  const svgRef = useRef(null)
  const sim = useRef(null)
  const simNodes = useRef(new Map())
  const drag = useRef(null)
  const frame = useRef(0)
  const [, setTick] = useState(0)
  const [packets, setPackets] = useState([])
  const [pulses, setPulses] = useState([])

  const nodes = snapshot?.nodes ?? []
  const links = snapshot?.links ?? []
  const topologyKey = useMemo(
    () => nodes.map((n) => n.id).join(',') + '|' + links.map((l) => `${l.a}-${l.b}`).join(','),
    [nodes, links],
  )

  // ---- force layout -------------------------------------------------------
  useEffect(() => {
    const existing = simNodes.current
    const next = new Map()
    nodes.forEach((n) => {
      const prev = existing.get(n.id)
      next.set(n.id, prev
        ? Object.assign(prev, { hx: n.x * W, hy: n.y * H })
        : { id: n.id, x: n.x * W, y: n.y * H, hx: n.x * W, hy: n.y * H })
    })
    simNodes.current = next
    const list = [...next.values()]
    const edges = links.map((l) => ({ source: l.a, target: l.b }))

    if (!sim.current) {
      sim.current = forceSimulation()
        .force('charge', forceManyBody().strength(-380))
        .force('collide', forceCollide(42))
        .alphaDecay(0.035)
        .on('tick', () => {
          cancelAnimationFrame(frame.current)
          frame.current = requestAnimationFrame(() => setTick((t) => t + 1))
        })
    }
    sim.current
      .nodes(list)
      .force('link', forceLink(edges).id((d) => d.id).distance(120).strength(0.22))
      .force('x', forceX((d) => d.hx).strength(0.14))
      .force('y', forceY((d) => d.hy).strength(0.14))
      .alpha(0.7)
      .restart()
  }, [topologyKey]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => { sim.current?.stop(); cancelAnimationFrame(frame.current) }, [])

  const pos = useCallback((id) => {
    const n = simNodes.current.get(id)
    if (!n) return null
    return { x: Math.max(40, Math.min(W - 40, n.x)), y: Math.max(46, Math.min(H - 46, n.y)) }
  }, [])

  // ---- packets and pulses, driven straight from the event stream -------------
  useEffect(() => {
    if (!animate) return undefined
    let seq = 0
    return subscribe((e) => {
      const here = pos(e.node)
      if (!here) return
      const id = `${e.seq}-${seq++}`
      if ((e.kind === 'sent' || e.kind === 'forward' || e.kind === 'sf_flush') && e.peer) {
        const there = pos(e.peer)
        if (!there) return
        setPackets((p) => [...p.slice(-50), { id, from: here, to: there, priority: e.priority ?? 1 }])
      } else if (['recv', 'ack', 'retry', 'sf_queue', 'peer_down', 'peer_up'].includes(e.kind) || e.kind.startsWith('drop_')) {
        const tone = e.kind === 'recv' || e.kind === 'ack' || e.kind === 'peer_up' ? '#2f6f4a' : e.kind === 'retry' || e.kind === 'sf_queue' ? '#a36a12' : '#c13a30'
        setPulses((p) => [...p.slice(-30), { id, at: here, tone, big: e.kind === 'recv' }])
      }
    })
  }, [animate, subscribe, pos])

  // ---- dragging --------------------------------------------------------------
  const toSvg = (event) => {
    const svg = svgRef.current
    const pt = svg.createSVGPoint()
    pt.x = event.clientX
    pt.y = event.clientY
    return pt.matrixTransform(svg.getScreenCTM().inverse())
  }
  const onPointerDown = (id) => (event) => {
    event.currentTarget.setPointerCapture?.(event.pointerId)
    drag.current = { id, moved: false, start: toSvg(event) }
  }
  const onPointerMove = (event) => {
    const d = drag.current
    if (!d) return
    const p = toSvg(event)
    if (!d.moved && Math.hypot(p.x - d.start.x, p.y - d.start.y) < 5) return
    d.moved = true
    const node = simNodes.current.get(d.id)
    node.fx = p.x
    node.fy = p.y
    sim.current?.alphaTarget(0.25).restart()
  }
  const onPointerUp = () => {
    const d = drag.current
    drag.current = null
    if (!d) return
    const node = simNodes.current.get(d.id)
    if (node) { node.fx = null; node.fy = null }
    sim.current?.alphaTarget(0)
    if (!d.moved) onSelect?.(d.id)
  }

  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes])
  const highlighted = useMemo(() => {
    const out = []
    highlight.forEach((h, i) => (h.path ?? []).slice(1).forEach((b, k) => out.push({ a: h.path[k], b, tone: h.tone ?? 'crimson', layer: i })))
    return out
  }, [highlight])

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${W} ${H}`}
      style={{ aspectRatio: `${W} / ${H}`, maxHeight: height, touchAction: 'none' }}
      className="mx-auto block w-full select-none"
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerLeave={onPointerUp}
      role="img"
      aria-label="Live mesh topology"
    >
      <defs>
        <pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse">
          <circle cx="1" cy="1" r="1" fill="#efe4da" />
        </pattern>
      </defs>
      <rect width={W} height={H} fill="url(#grid)" rx="18" />

      {/* links */}
      {links.map((l) => {
        const a = pos(l.a)
        const b = pos(l.b)
        if (!a || !b) return null
        const q = l.quality ?? 1 - l.loss
        const up = l.up
        const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
        return (
          <g key={`${l.a}-${l.b}`} onClick={onLinkClick ? () => onLinkClick(l) : undefined} style={{ cursor: onLinkClick ? 'pointer' : 'default' }}>
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth="16" />
            <line
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={up ? '#c4a58b' : '#e4d6ca'}
              strokeWidth={up ? 1.2 + q * 3.4 : 1.4}
              strokeLinecap="round"
              strokeDasharray={up ? undefined : '3 6'}
              opacity={up ? 0.85 : 0.7}
              style={{ transition: 'stroke-width 400ms, stroke 400ms' }}
            />
            {showLoss && l.loss > 0 && (
              <text x={mid.x} y={mid.y - 6} textAnchor="middle" className="fill-muted" fontSize="10.5" fontFamily="JetBrains Mono, monospace" paintOrder="stroke" stroke="#fff" strokeWidth="3">
                {Math.round(l.loss * 100)}%
              </text>
            )}
          </g>
        )
      })}

      {/* highlighted paths */}
      {highlighted.map((h, i) => {
        const a = pos(h.a)
        const b = pos(h.b)
        if (!a || !b) return null
        const color = h.tone === 'brown' ? '#6f4e34' : '#c13a30'
        return (
          <g key={`${h.a}-${h.b}-${i}`} style={{ pointerEvents: 'none' }}>
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={color} strokeOpacity="0.18" strokeWidth={h.layer ? 9 : 11} strokeLinecap="round" />
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={color} strokeWidth={h.layer ? 2.4 : 3.2} strokeLinecap="round"
                  strokeDasharray="7 5" style={{ animation: 'dash-flow 1.1s linear infinite' }} />
          </g>
        )
      })}

      {/* pulses */}
      <AnimatePresence>
        {pulses.map((p) => (
          <motion.circle
            key={p.id} cx={p.at.x} cy={p.at.y} fill="none" stroke={p.tone} strokeWidth="2"
            initial={{ r: 20, opacity: 0.8 }} animate={{ r: p.big ? 52 : 38, opacity: 0 }} exit={{ opacity: 0 }}
            transition={{ duration: p.big ? 0.9 : 0.6, ease: 'easeOut' }}
            onAnimationComplete={() => setPulses((all) => all.filter((x) => x.id !== p.id))}
            style={{ pointerEvents: 'none' }}
          />
        ))}
      </AnimatePresence>

      {/* nodes */}
      {nodes.map((n) => {
        const p = pos(n.id)
        if (!p) return null
        const off = !n.online
        const stroke = off ? '#d9c7ba' : ROLE_STROKE[n.role] ?? '#8a6444'
        const isSel = selected === n.id
        const r = n.role === 'NORMAL' ? 20 : 23
        return (
          <g
            key={n.id}
            transform={`translate(${p.x} ${p.y})`}
            onPointerDown={onPointerDown(n.id)}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect?.(n.id)}
            tabIndex={0}
            role="button"
            aria-label={`${n.id}, ${n.label}, ${off ? 'switched off' : 'online'}`}
            style={{ cursor: 'grab', outline: 'none', opacity: off && dimOffline ? 0.62 : 1, transition: 'opacity 400ms' }}
          >
            {isSel && <circle r={r + 8} fill="none" stroke="#c13a30" strokeWidth="2" strokeDasharray="4 4" style={{ animation: 'dash-flow 2s linear infinite' }} />}
            {n.role !== 'NORMAL' && !off && <circle r={r + 4} fill="none" stroke={stroke} strokeOpacity="0.35" strokeWidth="1.5" />}
            <circle r={r} fill={off ? '#f6eee8' : n.role === 'RESCUE' ? '#6e1a16' : n.role === 'GATEWAY' ? '#a62b23' : '#fff'} stroke={stroke} strokeWidth={2.2}
                    style={{ transition: 'fill 400ms, stroke 400ms' }} />
            <text textAnchor="middle" dy="4" fontSize="12.5" fontWeight="600" fontFamily="JetBrains Mono, monospace"
                  fill={off ? '#8a766a' : n.role === 'NORMAL' ? '#2b1a13' : '#fff'}>
              {n.id}
            </text>
            {off && (
              <g stroke="#a62b23" strokeWidth="2" strokeLinecap="round">
                <line x1="-6" y1="-6" x2="6" y2="6" transform="translate(13 -15)" />
                <line x1="6" y1="-6" x2="-6" y2="6" transform="translate(13 -15)" />
              </g>
            )}
            {n.store_forward > 0 && (
              <g transform="translate(15 -17)">
                <circle r="9" fill="#a36a12" stroke="#fff" strokeWidth="2" />
                <text textAnchor="middle" dy="3.5" fontSize="10" fontWeight="700" fill="#fff">{n.store_forward}</text>
              </g>
            )}
            <text y={r + 15} textAnchor="middle" fontSize="11" className="fill-ink-soft" paintOrder="stroke" stroke="#fff" strokeWidth="3.5">
              {n.label}
            </text>
          </g>
        )
      })}

      {/* travelling packets */}
      {packets.map((p) => {
        const d = PRIORITY_DOT[p.priority] ?? PRIORITY_DOT[1]
        return (
          <motion.g key={p.id} style={{ pointerEvents: 'none' }}
            initial={{ x: p.from.x, y: p.from.y, opacity: 1 }} animate={{ x: p.to.x, y: p.to.y }}
            transition={{ duration: p.priority === 0 ? 0.5 : 0.7, ease: 'easeInOut' }}
            onAnimationComplete={() => setPackets((all) => all.filter((x) => x.id !== p.id))}>
            <circle r={d.r + 5} fill={d.glow} opacity="0.55" />
            <circle r={d.r} fill={d.fill} stroke="#fff" strokeWidth="1.5" />
          </motion.g>
        )
      })}
    </svg>
  )
}

export function GraphLegend() {
  const item = 'flex items-center gap-2'
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted">
      <span className={item}><i className="h-3 w-3 rounded-full border-2 border-brown-500 bg-white" /> Survivor</span>
      <span className={item}><i className="h-3 w-3 rounded-full border-2 border-crimson-600 bg-crimson-600" /> Gateway</span>
      <span className={item}><i className="h-3 w-3 rounded-full border-2 border-crimson-800 bg-crimson-800" /> Rescue</span>
      <span className={item}><i className="h-3 w-3 rounded-full border-2 border-line-strong bg-wash-2" /> Switched off</span>
      <span className={item}><i className="h-1 w-6 rounded bg-brown-300" /> Thicker = better link</span>
      <span className={item}><i className="h-2.5 w-2.5 rounded-full bg-crimson-500" /> SOS packet</span>
      <span className={item}><i className="h-2 w-2 rounded-full bg-brown-500" /> Normal packet</span>
      <span className={item}><i className="grid h-4 w-4 place-items-center rounded-full bg-warn text-[9px] font-bold text-white">3</i> Held in store-and-forward</span>
    </div>
  )
}
