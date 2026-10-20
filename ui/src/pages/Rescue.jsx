import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Activity, AlertOctagon, Clock, ListChecks, Siren, TowerControl } from 'lucide-react'
import MeshGraph, { GraphLegend } from '../components/MeshGraph'
import { PathChips, StatStrip } from '../components/parts'
import { Badge, Card, CardHeader, Empty, Mono, PageHeader, PriorityBadge, Table } from '../components/ui'
import { RESCUE_DST, ms } from '../lib/format'
import { useLab, useLive } from '../lib/lab'

function useNow(every = 1000) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), every); return () => clearInterval(t) }, [every])
  return now
}

function age(createdMs, now) {
  const s = Math.max(0, Math.round((now - createdMs) / 1000))
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`
}

function SosCard({ item, now, selected, onSelect }) {
  const fresh = now - item.created_ms < 6000
  return (
    <motion.li layout initial={{ opacity: 0, x: -14, backgroundColor: '#fdf1f0' }} animate={{ opacity: 1, x: 0, backgroundColor: selected ? '#fdf1f0' : '#ffffff' }} transition={{ duration: 0.5 }}
      onClick={onSelect} className="cursor-pointer border-b border-line px-5 py-4 last:border-0 hover:bg-wash">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className={`relative grid h-9 w-9 place-items-center rounded-full ${fresh ? 'bg-crimson-600' : 'bg-brown-800'} text-white`}>
            {fresh && <span className="absolute inset-0 rounded-full bg-crimson-500" style={{ animation: 'pulse-ring 1.4s ease-out infinite' }} />}
            <Siren size={16} className="relative" />
          </span>
          <div>
            <div className="flex items-center gap-2"><Mono className="text-sm font-semibold">{item.sender}</Mono><PriorityBadge priority={0} /></div>
            <div className="mt-0.5 text-[13px] text-ink-soft">{item.body}</div>
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="tabular font-display text-xl font-semibold text-crimson-700">{age(item.created_ms, now)}</div>
          <div className="text-[11px] uppercase tracking-wider text-muted">since sent</div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 pl-12">
        <PathChips path={item.route} />
        <span className="text-xs text-muted">{item.hops} relay{item.hops === 1 ? '' : 's'} · took {ms(item.latency_ms)}</span>
      </div>
    </motion.li>
  )
}

const OUTCOME_TONE = { delivered: 'ok', 'in flight': 'warn', 'held in store-and-forward': 'warn', failed: 'crimson' }

export default function Rescue() {
  const { snapshot, connected } = useLab()
  const { data } = useLive('/api/rescue', { every: 700 })
  const now = useNow()
  const [selected, setSelected] = useState(null)
  const [node, setNode] = useState(null)

  const route = useMemo(() => {
    const item = data?.sos_queue.find((m) => m.msg_id === selected) ?? data?.delivery_log.find((m) => m.msg_id === selected)
    return item ? [{ path: item.route }] : []
  }, [data, selected])

  if (!snapshot) return <div className="py-24 text-center text-muted">{connected ? 'Loading…' : 'Waiting for the EcoMesh server…'}</div>
  const terminals = snapshot.nodes.filter((n) => n.role !== 'NORMAL')
  const unreached = data?.unreached_sos ?? []

  return (
    <div>
      <PageHeader eyebrow="Rescue dashboard" title="What the coordinators see"
        actions={
          <div className="flex items-center gap-2">
            {terminals.map((t) => (
              <Badge key={t.id} tone={t.online ? 'ok' : 'crimson'}><TowerControl size={12} /> {t.id} {t.role.toLowerCase()} {t.online ? 'up' : 'down'}</Badge>
            ))}
          </div>
        }>
        The moment a rescue team comes into range of any node, every pending SOS flows in with its sender and the path it took.
        Nobody searches room by room — the building tells them where people are.
      </PageHeader>

      <StatStrip stats={data?.stats ?? snapshot.stats} />

      <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div className="space-y-6">
          <Card className="overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3.5">
              <div className="flex items-center gap-2 text-[15px] font-semibold"><Activity size={16} className="text-crimson-600" /> Live mesh</div>
              <GraphLegend />
            </div>
            <div className="p-2"><MeshGraph snapshot={snapshot} selected={node} onSelect={setNode} highlight={route} height={430} /></div>
            {selected && route.length > 0 && <div className="border-t border-line bg-wash px-5 py-3 text-xs text-muted">Showing the route of the selected message. <button className="font-medium text-crimson-700 hover:underline" onClick={() => setSelected(null)}>Clear</button></div>}
          </Card>

          <Card>
            <CardHeader icon={ListChecks} title="Delivery log" subtitle="Every message the mesh has been asked to carry, newest first." />
            <Table
              rowKey={(r) => r.msg_id}
              onRowClick={(r) => setSelected(r.msg_id)}
              activeKey={selected}
              rows={(data?.delivery_log ?? []).slice(0, 40)}
              empty={<Empty icon={ListChecks} title="Nothing sent yet">Raise an SOS or send a message from the node view.</Empty>}
              columns={[
                { key: 'src', header: 'Source', render: (r) => <Mono className="font-semibold">{r.src}</Mono> },
                { key: 'dst', header: 'Destination', render: (r) => <Mono>{r.dst === RESCUE_DST ? (r.received_by ? `Rescue (${r.received_by})` : 'Rescue') : r.dst}</Mono> },
                { key: 'p', header: 'Priority', render: (r) => <PriorityBadge priority={r.priority} /> },
                { key: 'path', header: 'Hop path', render: (r) => <span className="font-mono text-xs">{r.route.join(' → ')}</span> },
                { key: 'out', header: 'Outcome', render: (r) => <Badge tone={OUTCOME_TONE[r.outcome] ?? 'neutral'}>{r.outcome}</Badge> },
                { key: 'lat', header: 'Latency', className: 'text-right', render: (r) => <span className="tabular">{ms(r.latency_ms)}</span> },
              ]}
            />
          </Card>
        </div>

        <div className="space-y-6">
          <Card className="overflow-hidden">
            <CardHeader icon={Siren} title="SOS queue" subtitle="Most urgent first, then longest waiting."
              action={<Badge tone="crimson">{data?.sos_queue.length ?? 0} received</Badge>} />
            {data?.sos_queue.length ? (
              <ul>
                <AnimatePresence initial={false}>
                  {data.sos_queue.map((m) => <SosCard key={m.msg_id} item={m} now={now} selected={selected === m.msg_id} onSelect={() => setSelected(m.msg_id)} />)}
                </AnimatePresence>
              </ul>
            ) : (
              <Empty icon={Siren} title="No SOS has reached rescue yet">When someone holds the SOS button on the node view, it appears here with the route it took.</Empty>
            )}
          </Card>

          <Card className={unreached.length ? 'border-warn/40' : ''}>
            <CardHeader icon={AlertOctagon} title="Not yet reached" subtitle="SOS raised somewhere but still held in a retention queue (simulator view — a real dashboard couldn't see these)."
              action={<Badge tone={unreached.length ? 'warn' : 'neutral'}>{unreached.length}</Badge>} />
            {unreached.length ? (
              <ul className="divide-y divide-line/70">
                {unreached.map((m) => (
                  <li key={m.msg_id} className="flex items-center justify-between gap-3 px-5 py-3 text-[13px]">
                    <div><Mono className="font-semibold">{m.sender}</Mono> <span className="text-muted">· {m.body}</span></div>
                    <div className="flex items-center gap-3"><Badge tone="warn">{m.status === 'queued_sf' ? 'held' : m.status}</Badge><span className="tabular text-muted"><Clock size={12} className="mr-1 inline" />{age(m.created_ms, now)}</span></div>
                  </li>
                ))}
              </ul>
            ) : <div className="px-5 py-6 text-center text-sm text-muted">Every SOS has been delivered.</div>}
          </Card>
        </div>
      </div>
    </div>
  )
}
