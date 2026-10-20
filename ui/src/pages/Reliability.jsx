import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Database, FlaskConical, Gauge, History, Inbox, RefreshCw, ShieldCheck, TimerReset } from 'lucide-react'
import { PathChips } from '../components/parts'
import { Badge, Button, Callout, Card, CardHeader, Empty, Field, Mono, PageHeader, PriorityBadge, Select, Table, cx } from '../components/ui'
import { api } from '../lib/api'
import { EVENT_LABEL, RESCUE_DST, eventTone, ms, shortId } from '../lib/format'
import { useAction, useLab, useLive } from '../lib/lab'

const PAIRS = [
  ['TTL', 'Decrement at each hop, drop at 0', 'A misrouted message circulating forever', 'drop_ttl'],
  ['Dedup set', 'msg_id (+ type, attempt) → first seen, expires in 300 s', 'One message multiplying into thousands of copies', 'drop_dup'],
  ['ACK + retry', 'Destination ACKs; sender retries up to 3×, recomputing the route each time', 'The sender never learning help was reached; retrying down a dead path', 'retry'],
  ['Heartbeat', 'A node silent for 10 s is removed from the graph', 'Routing through a device that died ten minutes ago', 'peer_down'],
  ['Path list', 'Loop detected if your own id is already on it', 'Loops TTL alone would only catch after 10 wasted hops', 'drop_loop'],
  ['Store-and-forward', 'Queue when no path exists, flush when one appears', 'Messages dying when help was 30 seconds away', 'sf_queue'],
]

function PriorityTest({ sender }) {
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const run = async () => {
    setBusy(true); setError(null); setResult(null)
    try {
      const r = await api.post('/api/lab/burst', { src: sender, dst: RESCUE_DST, normal: 8, service_ms: 150 })
      const ids = [{ id: r.sos, sos: true }, ...r.normal.map((id, i) => ({ id, sos: false, n: i + 1 }))]
      // poll until they have all landed (or give up)
      for (let i = 0; i < 20; i++) {
        await new Promise((res) => setTimeout(res, 800))
        const details = await Promise.all(ids.map((m) => api.get(`/api/messages/${m.id}`)))
        if (details.every((d) => d.arrived) || i === 19) {
          const rows = ids.map((m, k) => ({ ...m, latency: details[k].latency_ms, route: details[k].route })).filter((m) => m.latency != null).sort((a, b) => a.latency - b.latency)
          setResult({ rows, total: ids.length })
          break
        }
      }
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const max = result ? Math.max(...result.rows.map((r) => r.latency)) : 1
  return (
    <Card>
      <CardHeader icon={Gauge} title="Priority at every hop" subtitle={`Eight routine messages, then one SOS — all from ${sender}, all at the same instant, through a slow radio. Which arrives first?`}
        action={<Button variant="primary" size="sm" busy={busy} onClick={run}>Run the test</Button>} />
      <div className="p-5">
        {error && <div className="text-sm text-crimson-600">{error}</div>}
        {!result && !busy && !error && <Empty icon={Gauge} title="Not run yet">The SOS is queued <i>last</i>. If priority works, it still arrives near the front — and it overtakes the backlog again at every relay.</Empty>}
        {busy && <div className="py-10 text-center text-sm text-muted">Messages are queueing at the radio…</div>}
        {result && (
          <ol className="space-y-2">
            {result.rows.map((r, i) => (
              <motion.li key={r.id} layout initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }} className="grid grid-cols-[28px_120px_1fr_70px] items-center gap-3 text-[13px]">
                <span className="tabular text-right font-semibold text-muted">#{i + 1}</span>
                <span className={cx('font-medium', r.sos ? 'text-crimson-700' : 'text-ink-soft')}>{r.sos ? 'SOS (sent last)' : `routine ${r.n}`}</span>
                <div className="h-5 overflow-hidden rounded-md bg-wash"><motion.div className={cx('h-full rounded-md', r.sos ? 'bg-crimson-600' : 'bg-brown-300')} initial={{ width: 0 }} animate={{ width: `${(r.latency / max) * 100}%` }} transition={{ duration: 0.6, delay: i * 0.05 }} /></div>
                <span className="tabular text-right text-muted">{ms(r.latency)}</span>
              </motion.li>
            ))}
            <li className="pt-2 text-xs text-muted">{result.rows.length} of {result.total} landed. The radio is restored to full speed afterwards.</li>
          </ol>
        )}
      </div>
    </Card>
  )
}

function Timeline({ messages }) {
  const [id, setId] = useState(null)
  useEffect(() => { if (!id && messages.length) setId(messages[0].msg_id) }, [messages, id])
  const { data } = useLive(id ? `/api/messages/${id}` : null, { every: 1200 })
  return (
    <Card>
      <CardHeader icon={History} title="One message, every log" subtitle="Each node's event table, stitched together by msg_id." />
      <div className="p-5">
        <Field label="Message">
          <Select value={id ?? ''} onChange={(e) => setId(e.target.value)}>
            {messages.map((m) => <option key={m.msg_id} value={m.msg_id}>{shortId(m.msg_id)} · {m.src} → {m.dst === RESCUE_DST ? 'Rescue' : m.dst} · {m.priority_name} · {m.outcome}</option>)}
          </Select>
        </Field>
        {!messages.length && <Empty icon={Inbox} title="No messages yet">Send something from the node view or run the priority test.</Empty>}
        {data && (
          <div className="mt-5">
            <div className="mb-4 flex flex-wrap items-center gap-3"><PathChips path={data.route} /><Badge tone={data.arrived ? 'ok' : 'warn'}>{data.arrived ? `arrived in ${ms(data.latency_ms)}` : data.origin.status}</Badge></div>
            <ol className="relative ml-2 border-l border-line-strong pl-6">
              {data.events.filter((e) => e.kind !== 'route_change').map((e) => (
                <li key={`${e.node}-${e.id}`} className="relative pb-3.5">
                  <span className={cx('absolute -left-[31px] top-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-white', { bad: 'bg-crimson-500', good: 'bg-ok', warn: 'bg-warn', neutral: 'bg-brown-400' }[eventTone(e.kind)])} />
                  <div className="flex flex-wrap items-baseline gap-x-3 text-[13px]">
                    <span className="tabular w-16 text-muted">+{e.t_ms} ms</span>
                    <Mono className="font-semibold">{e.node}</Mono>
                    <span className="font-medium">{EVENT_LABEL[e.kind] ?? e.kind}</span>
                    {e.peer && <span className="text-muted">→ <Mono>{e.peer}</Mono></span>}
                    {e.detail && <span className="text-muted">{e.detail}</span>}
                  </div>
                </li>
              ))}
            </ol>
            {data.wire && (
              <div className="mt-2 rounded-xl bg-wash px-4 py-3 text-[13px] text-ink-soft">
                <b>What a relay saw of the payload</b> ({data.wire.payload_len} bytes{data.wire.encrypted ? ', encrypted' : ', plaintext'}{data.wire.signed ? ', signed' : ''}):{' '}
                <Mono className="break-all text-muted">{data.wire.payload_hex}…</Mono>
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  )
}

export default function Reliability() {
  const { snapshot, connected } = useLab()
  const [nodeId, setNodeId] = useState(null)
  useEffect(() => { if (snapshot && !nodeId) setNodeId(snapshot.config.sender || snapshot.nodes[0]?.id) }, [snapshot, nodeId])
  const { data: view } = useLive(nodeId ? `/api/nodes/${nodeId}` : null, { every: 800 })
  const { data: stats } = useLive('/api/stats', { every: 1500 })
  const { data: rescue } = useLive('/api/rescue', { every: 1500 })

  if (!snapshot) return <div className="py-24 text-center text-muted">{connected ? 'Loading…' : 'Waiting for the EcoMesh server…'}</div>
  const q = view?.queues
  const counts = { retry: view?.counters.retry, sf_queue: view?.counters.sf_queue, drop_dup: view?.counters.drop_dup, peer_down: view?.counters.peer_down }

  return (
    <div>
      <PageHeader eyebrow="Reliability" title="Each mechanism exists to prevent one specific failure">
        Learn them as pairs. The numbers beside each are live counts from the selected node's event log, so you can set a mechanism off and watch it count.
      </PageHeader>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader icon={ShieldCheck} title="Mechanism and the failure it prevents" action={
            <Select value={nodeId ?? ''} onChange={(e) => setNodeId(e.target.value)} className="!h-8 !w-auto !text-xs">{snapshot.nodes.map((n) => <option key={n.id} value={n.id}>{n.id} · {n.label}</option>)}</Select>} />
          <ul className="divide-y divide-line/70">
            {PAIRS.map(([name, how, prevents, key]) => (
              <li key={name} className="grid grid-cols-[1fr_auto] items-start gap-4 px-5 py-4">
                <div>
                  <div className="text-sm font-semibold">{name}</div>
                  <div className="mt-0.5 text-[13px] text-muted">{how}</div>
                  <div className="mt-1.5 text-[13px] text-crimson-700">Prevents: {prevents}</div>
                </div>
                <div className="text-right"><div className="tabular font-display text-2xl font-semibold">{counts[key] ?? (key === 'drop_ttl' || key === 'drop_loop' ? stats?.drops?.[key.replace('drop_', '')] ?? 0 : '—')}</div><div className="text-[11px] uppercase tracking-wider text-muted">{nodeId} count</div></div>
              </li>
            ))}
          </ul>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader icon={Database} title={`${nodeId ?? '…'} · store-and-forward`} subtitle={view?.online ? `Holding ${q?.store_forward.length ?? 0} of ${q?.store_forward_limit ?? 500} (oldest lowest-priority evicted first).` : 'Node is off; its in-memory queue was lost.'} />
            <Table rowKey={(m) => m.msg_id} rows={q?.store_forward ?? []}
              empty={<Empty icon={Inbox} title="Nothing held">Messages appear here when there is no route — try switching the gateway off on the Live demo page.</Empty>}
              columns={[
                { key: 'id', header: 'Message', render: (m) => <Mono>{shortId(m.msg_id)}</Mono> },
                { key: 'dst', header: 'To', render: (m) => <Mono>{m.dst === RESCUE_DST ? 'RESCUE' : m.dst}</Mono> },
                { key: 'p', header: 'Priority', render: (m) => <PriorityBadge priority={m.priority} /> },
                { key: 'a', header: 'Held', className: 'text-right', render: (m) => <span className="tabular">{m.age_s}s</span> },
              ]} />
          </Card>
          <Card>
            <CardHeader icon={TimerReset} title="Awaiting ACK" subtitle={q ? `Timeout ${q.ack_timeout_s}s · up to ${q.max_retries} attempts, route recomputed each time.` : ''} />
            <Table rowKey={(m) => m.msg_id} rows={q?.pending_acks ?? []}
              empty={<div className="px-5 py-6 text-center text-sm text-muted">Everything sent has been acknowledged.</div>}
              columns={[
                { key: 'id', header: 'Message', render: (m) => <Mono>{shortId(m.msg_id)}</Mono> },
                { key: 'dst', header: 'To', render: (m) => <Mono>{m.dst === RESCUE_DST ? 'RESCUE' : m.dst}</Mono> },
                { key: 'nh', header: 'Via', render: (m) => <Mono>{m.next_hop}</Mono> },
                { key: 'at', header: 'Attempt', className: 'text-right', render: (m) => <Badge tone={m.attempts > 1 ? 'warn' : 'neutral'}>{m.attempts}/{q.max_retries}</Badge> },
              ]} />
          </Card>
        </div>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <PriorityTest sender={snapshot.config.sender || snapshot.nodes[0].id} />
        <Timeline messages={rescue?.delivery_log ?? []} />
      </div>

      {stats && (
        <Card className="mt-6">
          <CardHeader icon={RefreshCw} title="Mesh-wide counters" subtitle="Summed over every node's event table." />
          <div className="grid grid-cols-2 divide-line sm:grid-cols-4 sm:divide-x">
            {[['Retries', stats.retries], ['Queued for later', stats.store_forward_queued], ['Flushed', stats.store_forward_flushed], ['Dedup drop ratio', stats.dedup_drop_ratio == null ? '—' : `${(stats.dedup_drop_ratio * 100).toFixed(1)}%`]].map(([k, v]) => (
              <div key={k} className="border-b border-line px-5 py-4 sm:border-b-0"><div className="text-[11px] font-semibold uppercase tracking-wider text-muted">{k}</div><div className="tabular mt-1 font-display text-2xl font-semibold">{v}</div></div>
            ))}
          </div>
          {Object.keys(stats.drops).length > 0 && <div className="flex flex-wrap gap-2 border-t border-line px-5 py-3 text-xs text-muted">Drops: {Object.entries(stats.drops).map(([k, v]) => <Badge key={k} tone="neutral">{k} · {v}</Badge>)}</div>}
        </Card>
      )}
    </div>
  )
}
