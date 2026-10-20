import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ArrowRight, Radio } from 'lucide-react'
import { Badge, Card, Empty, Mono, PriorityBadge, Stat, cx } from './ui'
import { EVENT_LABEL, clock, eventTone, num, pct, shortId } from '../lib/format'

/** The rescue dashboard's live stat strip (section 12.2). */
export function StatStrip({ stats, compact }) {
  if (!stats) return null
  const cells = [
    { label: 'Delivery ratio', value: pct(stats.delivery_ratio), hint: `${stats.delivered} of ${stats.sent} messages`, tone: stats.delivery_ratio >= 0.9 ? 'ok' : undefined },
    { label: 'Mean relays', value: num(stats.mean_hops, 1), hint: 'nodes between sender and receiver' },
    { label: 'Nodes online', value: `${stats.nodes_online}/${stats.nodes_total}`, hint: stats.nodes_online < stats.nodes_total ? `${stats.nodes_total - stats.nodes_online} switched off` : 'whole mesh up' },
    { label: 'SOS delivered', value: `${stats.sos_delivered}/${stats.sos_sent}`, tone: 'crimson', hint: 'rescue has been told' },
    { label: 'Held in store-and-forward', value: stats.queued_in_store_forward, hint: 'waiting for a route', tone: stats.queued_in_store_forward ? 'crimson' : undefined },
    { label: 'Retries', value: stats.retries, hint: 'ACK timeouts recovered' },
  ]
  return (
    <Card className={cx('grid grid-cols-2 divide-line sm:grid-cols-3 lg:grid-cols-6 lg:divide-x', compact ? 'p-0' : '')}>
      {cells.map((c) => (
        <div key={c.label} className="border-b border-line px-5 py-4 lg:border-b-0">
          <Stat {...c} />
        </div>
      ))}
    </Card>
  )
}

/** A route drawn as chips that build up hop by hop (the "moment the user sees the mesh work"). */
export function PathChips({ path, tone = 'crimson', className }) {
  if (!path?.length) return null
  return (
    <div className={cx('flex flex-wrap items-center gap-1', className)}>
      {path.map((id, i) => (
        <motion.span key={`${id}-${i}`} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.09 }} className="flex items-center gap-1">
          <span className={cx('rounded-md px-2 py-0.5 font-mono text-xs font-semibold',
            i === 0 ? 'bg-brown-800 text-white' : i === path.length - 1 ? (tone === 'crimson' ? 'bg-crimson-600 text-white' : 'bg-brown-600 text-white') : 'bg-brown-100 text-brown-700')}>
            {id}
          </span>
          {i < path.length - 1 && <ArrowRight size={12} className="text-brown-300" />}
        </motion.span>
      ))}
    </div>
  )
}

const TONE_CLASS = { bad: 'text-crimson-600', good: 'text-ok', warn: 'text-warn', neutral: 'text-ink-soft' }

/** Scrolling log of what the engine just did, straight from each node's event table. */
export function EventFeed({ events, nodeFilter, limit = 60, height = 360, title = 'Engine events' }) {
  const [chatter, setChatter] = useState(false)
  const rows = useMemo(() => {
    const filtered = events.filter((e) => (chatter || (e.kind !== 'route_change' && e.kind !== 'peer_up')) && (!nodeFilter || e.node === nodeFilter))
    return filtered.slice(-limit).reverse()
  }, [events, chatter, nodeFilter, limit])
  return (
    <Card className="flex flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
        <div className="flex items-center gap-2 text-[15px] font-semibold"><Radio size={16} className="text-crimson-600" /> {title}</div>
        <label className="flex cursor-pointer items-center gap-2 text-xs text-muted">
          <input type="checkbox" checked={chatter} onChange={(e) => setChatter(e.target.checked)} className="accent-crimson-600" />
          routing chatter
        </label>
      </div>
      <div style={{ height }} className="overflow-y-auto">
        {rows.length === 0 ? (
          <Empty icon={Radio} title="Quiet so far">Send a message or switch a node off and the engine's events appear here as they are logged.</Empty>
        ) : (
          <ul className="divide-y divide-line/70">
            <AnimatePresence initial={false}>
              {rows.map((e) => (
                <motion.li key={e.seq ?? `${e.node}-${e.id}`} layout initial={{ opacity: 0, backgroundColor: '#fdf1f0' }} animate={{ opacity: 1, backgroundColor: '#ffffff' }} transition={{ duration: 0.8 }}
                  className="flex items-center gap-3 px-5 py-2 text-[12.5px]">
                  <Mono className="w-[86px] shrink-0 text-muted">{clock(e.ts_ms)}</Mono>
                  <Mono className="w-9 shrink-0 font-semibold text-ink">{e.node}</Mono>
                  <span className={cx('w-40 shrink-0 font-medium', TONE_CLASS[eventTone(e.kind)])}>{EVENT_LABEL[e.kind] ?? e.kind}</span>
                  <span className="flex min-w-0 flex-1 items-center gap-2 truncate text-muted">
                    {e.peer && <span>→ <Mono>{e.peer}</Mono></span>}
                    {e.msg_id && <Mono className="text-brown-400">{shortId(e.msg_id)}</Mono>}
                    {e.detail && <span className="truncate">{e.detail}</span>}
                  </span>
                  {e.priority != null && e.priority !== 1 && <PriorityBadge priority={e.priority} />}
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        )}
      </div>
    </Card>
  )
}

export function RoleBadge({ role }) {
  if (role === 'GATEWAY') return <Badge tone="crimson">Gateway</Badge>
  if (role === 'RESCUE') return <Badge tone="dark">Rescue</Badge>
  return <Badge tone="neutral">Survivor</Badge>
}

/** Colour-banded hex bytes for the protocol inspector. */
export function HexView({ hex, regions, fields, active, onActive }) {
  const bytes = useMemo(() => (hex.match(/../g) ?? []), [hex])
  const regionOf = (i) => regions.find((r) => i >= r.start && i < r.end)?.name
  const fieldOf = (i) => fields.find((f) => i >= f.offset && i < f.offset + f.size)?.name
  const REGION_STYLE = {
    header: 'bg-brown-100 text-brown-800',
    path: 'bg-warn-bg text-warn',
    payload: 'bg-crimson-50 text-crimson-700',
    signature: 'bg-ok-bg text-ok',
  }
  return (
    <div className="font-mono text-[13px] leading-8">
      <div className="grid grid-cols-[repeat(16,minmax(0,1fr))] gap-x-1 gap-y-0.5">
        {bytes.map((b, i) => {
          const f = i < 52 ? fieldOf(i) : null
          return (
            <span
              key={i}
              onMouseEnter={() => f && onActive?.(f)}
              onMouseLeave={() => onActive?.(null)}
              className={cx('rounded text-center transition-colors', REGION_STYLE[regionOf(i)] ?? 'bg-wash', active && f === active && 'bg-crimson-600 text-white ring-2 ring-crimson-200')}
            >
              {b}
            </span>
          )
        })}
      </div>
    </div>
  )
}
