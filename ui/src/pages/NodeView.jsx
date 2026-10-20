import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { CheckCheck, Clock, Radio, Send, Siren, Users, WifiOff } from 'lucide-react'
import MeshGraph from '../components/MeshGraph'
import { PathChips, RoleBadge } from '../components/parts'
import { Badge, Button, Card, CardHeader, Empty, Input, Mono, PriorityBadge, Select, StatusPill, cx } from '../components/ui'
import { api } from '../lib/api'
import { RESCUE_DST, ago, describeStatus } from '../lib/format'
import { useAction, useLab, useLive } from '../lib/lab'

const HOLD_MS = 1300

/** Long-press to arm: a ring fills while the button is held; letting go early cancels. */
function SosButton({ disabled, onFire, lastSentAt }) {
  const [progress, setProgress] = useState(0)
  const [holding, setHolding] = useState(false)
  const raf = useRef(0)
  const start = useRef(0)
  const fired = useRef(false)

  const stop = useCallback(() => {
    cancelAnimationFrame(raf.current)
    setHolding(false)
    setProgress(0)
  }, [])

  const tick = useCallback(() => {
    const p = Math.min(1, (performance.now() - start.current) / HOLD_MS)
    setProgress(p)
    if (p >= 1) {
      if (!fired.current) { fired.current = true; onFire() }
      stop()
      return
    }
    raf.current = requestAnimationFrame(tick)
  }, [onFire, stop])

  const begin = () => {
    if (disabled) return
    fired.current = false
    start.current = performance.now()
    setHolding(true)
    raf.current = requestAnimationFrame(tick)
  }
  useEffect(() => () => cancelAnimationFrame(raf.current), [])

  const R = 92
  const C = 2 * Math.PI * R
  const recentlySent = lastSentAt && Date.now() - lastSentAt < 2500

  return (
    <div className="flex flex-col items-center">
      <div className="relative grid h-[230px] w-[230px] place-items-center">
        {!disabled && !holding && <span className="absolute inset-4 rounded-full bg-crimson-500/20" style={{ animation: 'pulse-ring 2.4s ease-out infinite' }} />}
        <svg className="absolute inset-0 -rotate-90" viewBox="0 0 200 200" aria-hidden="true">
          <circle cx="100" cy="100" r={R} fill="none" stroke="#f2b3ad" strokeOpacity=".5" strokeWidth="6" />
          <circle cx="100" cy="100" r={R} fill="none" stroke="#8a211b" strokeWidth="6" strokeLinecap="round" strokeDasharray={C} strokeDashoffset={C * (1 - progress)} />
        </svg>
        <motion.button
          onPointerDown={begin}
          onPointerUp={stop}
          onPointerLeave={stop}
          onPointerCancel={stop}
          onKeyDown={(e) => { if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) begin() }}
          onKeyUp={(e) => { if (e.key === ' ' || e.key === 'Enter') stop() }}
          onContextMenu={(e) => e.preventDefault()}
          disabled={disabled}
          animate={{ scale: holding ? 0.94 : 1 }}
          transition={{ type: 'spring', stiffness: 400, damping: 22 }}
          aria-label="Hold to send an SOS"
          className={cx('relative z-10 grid h-[168px] w-[168px] select-none place-items-center rounded-full text-white shadow-[0_18px_40px_-14px_rgba(138,33,27,0.7)] transition-colors',
            disabled ? 'bg-line-strong' : holding ? 'bg-crimson-700' : 'bg-crimson-600 hover:bg-crimson-500')}
          style={{ touchAction: 'none', WebkitTouchCallout: 'none', animation: !disabled && !holding ? 'sos-throb 2.4s ease-in-out infinite' : undefined }}
        >
          <span className="flex flex-col items-center">
            {recentlySent ? <CheckCheck size={42} strokeWidth={2.4} /> : <Siren size={42} strokeWidth={2.2} />}
            <span className="mt-2 font-display text-[26px] font-semibold leading-none tracking-wide">{recentlySent ? 'SENT' : 'SOS'}</span>
          </span>
        </motion.button>
      </div>
      <div className="mt-1 h-5 text-[13px] font-medium text-ink-soft">
        {disabled ? 'This phone is switched off' : holding ? 'Keep holding…' : 'Press and hold to send'}
      </div>
    </div>
  )
}

function Bubble({ m, peerLabel }) {
  const status = describeStatus(m)
  const mine = m.direction === 'sent'
  const route = mine ? [m.src, ...m.relays] : [m.src, ...m.relays, m.dst === RESCUE_DST ? '' : m.dst].filter(Boolean)
  const tail = mine ? (m.dst === RESCUE_DST ? 'Rescue' : m.dst) : null
  return (
    <motion.li layout initial={{ opacity: 0, y: 10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} className={cx('flex flex-col', mine ? 'items-end' : 'items-start')}>
      <div className={cx('max-w-[92%] rounded-2xl px-4 py-3', mine ? (m.priority === 0 ? 'bg-crimson-600 text-white' : 'bg-brown-800 text-white') : 'border border-line bg-white text-ink')}>
        <div className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider opacity-80">
          {mine ? `to ${m.dst === RESCUE_DST ? 'Rescue' : peerLabel(m.dst)}` : `from ${peerLabel(m.src)}`}
          {m.priority !== 1 && <span className="rounded bg-white/20 px-1.5 py-0.5">{m.priority_name}</span>}
        </div>
        <div className="text-[15px] leading-snug">{m.body}</div>
      </div>
      <div className={cx('mt-1.5 flex max-w-[92%] flex-col gap-1.5', mine ? 'items-end' : 'items-start')}>
        <StatusPill status={status.key}>{status.label}</StatusPill>
        {(mine && m.status === 'delivered' || !mine) && route.length > 1 && (
          <div className="flex flex-wrap items-center gap-1">
            <PathChips path={tail ? [...route, tail] : route} tone={m.priority === 0 ? 'crimson' : 'brown'} />
          </div>
        )}
        <span className="text-[11px] text-muted">{ago(m.created_ms)}</span>
      </div>
    </motion.li>
  )
}

function Composer({ view, snapshot, onSent }) {
  const [dst, setDst] = useState(RESCUE_DST)
  const [text, setText] = useState('')
  const [priority, setPriority] = useState(1)
  const send = useAction(async () => {
    const out = await api.post(`/api/nodes/${view.id}/send`, { dst, text, priority })
    setText('')
    onSent?.()
    return out
  })
  const options = view.reachable
  useEffect(() => { if (dst !== RESCUE_DST && !options.some((o) => o.id === dst)) setDst(RESCUE_DST) }, [options, dst])
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) send.run() }} className="space-y-2.5">
      <div className="flex gap-2">
        <div className="min-w-0 flex-1">
          <Select value={dst} onChange={(e) => setDst(e.target.value)} className="!h-11" aria-label="Recipient">
            <option value={RESCUE_DST}>Rescue (any gateway)</option>
            {options.map((o) => <option key={o.id} value={o.id}>{o.id} · {o.hops} hop{o.hops === 1 ? '' : 's'}</option>)}
          </Select>
        </div>
        <div className="w-[116px] shrink-0">
          <Select value={priority} onChange={(e) => setPriority(Number(e.target.value))} className="!h-11" aria-label="Priority">
            <option value={1}>Normal</option><option value={0}>Urgent</option><option value={2}>Status</option>
          </Select>
        </div>
      </div>
      <div className="flex gap-2">
        <Input className="!h-12 !text-[15px]" value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. four of us in room 302, one injured" maxLength={400} disabled={!view.online} aria-label="Message" />
        <Button type="submit" variant="dark" className="!h-12 w-12 !px-0" busy={send.busy} disabled={!text.trim() || !view.online} aria-label="Send"><Send size={18} /></Button>
      </div>
      {send.error && <div className="text-xs text-crimson-600">{send.error}</div>}
    </form>
  )
}

export default function NodeView() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { snapshot, connected } = useLab()
  const fallback = snapshot?.config?.sender || snapshot?.nodes?.find((n) => n.role === 'NORMAL')?.id
  const nodeId = id || fallback
  const { data: view, reload } = useLive(nodeId ? `/api/nodes/${nodeId}` : null, { every: 500 })
  const [lastSos, setLastSos] = useState(null)
  const thread = useRef(null)

  const sos = useAction(async () => {
    const out = await api.post(`/api/nodes/${nodeId}/sos`)
    setLastSos(Date.now())
    reload()
    return out
  })

  useEffect(() => { thread.current?.scrollTo({ top: thread.current.scrollHeight, behavior: 'smooth' }) }, [view?.thread?.length])

  const labels = useMemo(() => Object.fromEntries((snapshot?.nodes ?? []).map((n) => [n.id, n.label])), [snapshot])
  const peerLabel = (pid) => pid

  if (!snapshot) return <div className="py-24 text-center text-muted">{connected ? 'Loading…' : 'Waiting for the EcoMesh server…'}</div>

  const online = view?.online
  const route = view?.rescue_route
  const lastSosMsg = view ? [...view.thread].reverse().find((m) => m.direction === 'sent' && m.priority === 0) : null

  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,430px)_minmax(0,1fr)] lg:items-start">
      {/* ---- the phone ---------------------------------------------------- */}
      <div className="mx-auto w-full max-w-[430px]">
        <div className="overflow-hidden rounded-[32px] border border-line-strong bg-white shadow-[0_30px_70px_-30px_rgba(63,44,30,0.35)]">
          <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
            <div className="flex min-w-0 flex-1 items-center gap-2.5">
              <Mono className="rounded-md bg-brown-800 px-2 py-1 text-sm font-semibold text-white">{nodeId}</Mono>
              <div className="min-w-0 leading-tight">
                <div className="truncate text-sm font-semibold">{labels[nodeId] ?? nodeId}</div>
                <div className="text-xs text-muted">{online ? 'on the mesh' : 'switched off'}</div>
              </div>
            </div>
            <Select value={nodeId} onChange={(e) => navigate(`/node/${e.target.value}`)} className="!h-9 !w-auto max-w-[46%] !text-xs" aria-label="Which phone">
              {snapshot.nodes.map((n) => <option key={n.id} value={n.id}>{n.id} · {n.label}</option>)}
            </Select>
          </div>

          <div className="px-5 pb-2 pt-6">
            {view && !online && (
              <div className="mb-4 flex items-center gap-2 rounded-xl bg-crimson-50 px-4 py-3 text-sm text-crimson-700"><WifiOff size={16} /> This phone is off. Switch it on from the Live demo page.</div>
            )}
            <SosButton disabled={!online || sos.busy} onFire={sos.run} lastSentAt={lastSos} />
            {sos.error && <div className="mt-2 text-center text-xs text-crimson-600">{sos.error}</div>}

            <AnimatePresence>
              {lastSosMsg && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="mt-4 overflow-hidden">
                  <div className="rounded-2xl border border-crimson-200 bg-crimson-50/50 px-4 py-3">
                    <div className="mb-1.5 flex items-center justify-between">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-crimson-700">Your last SOS</span>
                      <span className="text-[11px] text-muted">{ago(lastSosMsg.created_ms)}</span>
                    </div>
                    <StatusPill status={describeStatus(lastSosMsg).key}>{describeStatus(lastSosMsg).label}</StatusPill>
                    {lastSosMsg.status === 'delivered' && <PathChips className="mt-2" path={[lastSosMsg.src, ...lastSosMsg.relays, 'Rescue']} />}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* nearby + reachable */}
          <div className="mt-3 border-t border-line px-5 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-semibold"><Users size={16} className="text-crimson-600" /> {view ? (view.nearby === 0 ? 'No one nearby' : `${view.nearby} ${view.nearby === 1 ? 'person' : 'people'} nearby`) : '…'}</div>
              <Badge tone={route ? 'ok' : 'crimson'}>{route ? `Rescue reachable · ${route.hops} hops` : 'No route to rescue'}</Badge>
            </div>
            <ul className="mt-3 space-y-1.5">
              <AnimatePresence initial={false}>
                {(view?.reachable ?? []).map((p) => (
                  <motion.li layout key={p.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 8 }} className="flex items-center justify-between rounded-xl bg-wash px-3.5 py-2.5">
                    <div className="flex items-center gap-2.5"><Mono className="font-semibold">{p.id}</Mono><RoleBadge role={p.role} /></div>
                    <div className="flex items-center gap-1.5 text-xs text-muted">
                      {Array.from({ length: Math.min(p.hops, 5) }).map((_, i) => <span key={i} className="h-1.5 w-1.5 rounded-full bg-brown-400" />)}
                      <span className="tabular ml-1 font-medium text-ink-soft">{p.hops} hop{p.hops === 1 ? '' : 's'}</span>
                    </div>
                  </motion.li>
                ))}
              </AnimatePresence>
            </ul>
            {view && view.reachable.length === 0 && online && <div className="mt-3 text-[13px] text-muted">Nobody in range yet. Messages you send will be held until someone is.</div>}
          </div>

          {/* thread */}
          <div className="border-t border-line bg-white">
            <div ref={thread} className="max-h-[340px] min-h-[120px] overflow-y-auto px-5 py-4">
              {view?.thread?.length ? (
                <ul className="space-y-4">{view.thread.map((m) => <Bubble key={m.msg_id} m={m} peerLabel={peerLabel} />)}</ul>
              ) : (
                <Empty icon={Radio} title="No messages yet">Hold the SOS button, or write a message below.</Empty>
              )}
            </div>
            <div className="border-t border-line p-4">{view && <Composer view={view} snapshot={snapshot} onSent={reload} />}</div>
          </div>
        </div>
      </div>

      {/* ---- what the phone does not show ----------------------------------- */}
      <div className="space-y-6">
        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-[0.14em] text-crimson-600">Node view</div>
          <h1 className="font-display text-[34px] font-semibold leading-[1.1]">An emergency tool, not a chat app</h1>
          <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-ink-soft">
            Everything on the phone is one thing: <em>can I get a message out, and is it getting through?</em> The button needs a deliberate hold so a pocket can't fire it.
            Each message shows how far it travelled — the hop count is the moment you see the mesh working.
          </p>
        </div>
        <Card>
          <CardHeader icon={Clock} title="Under the hood" subtitle="Not part of the phone UI — what this node's engine is doing right now." />
          {view?.online ? (
            <div className="space-y-5 p-5">
              <div>
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">Heard directly (HELLO neighbours)</div>
                <div className="overflow-hidden rounded-xl border border-line">
                  <table className="w-full text-[13px]">
                    <tbody>
                      {view.neighbours.map((n) => (
                        <tr key={n.id} className="border-b border-line/70 last:border-0">
                          <td className="px-3 py-2 font-mono font-semibold">{n.id}</td>
                          <td className="px-3 py-2"><RoleBadge role={n.role} /></td>
                          <td className="px-3 py-2 text-right text-muted">link quality <span className="tabular font-medium text-ink-soft">{n.link_quality == null ? '—' : `${Math.round(n.link_quality * 100)}%`}</span></td>
                        </tr>
                      ))}
                      {!view.neighbours.length && <tr><td className="px-3 py-3 text-muted">No neighbours heard.</td></tr>}
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-3 text-center">
                {[['Held (S&F)', view.queues.store_forward.length], ['Awaiting ACK', view.queues.pending_acks.length], ['Dedup entries', view.queues.dedup_size]].map(([k, v]) => (
                  <div key={k} className="rounded-xl bg-wash px-3 py-3"><div className="font-display text-2xl font-semibold tabular">{v}</div><div className="mt-0.5 text-[11px] uppercase tracking-wider text-muted">{k}</div></div>
                ))}
              </div>
              {route && (
                <div>
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">Cheapest route to rescue · cost {route.cost}</div>
                  <PathChips path={route.path} />
                  <div className="mt-3 space-y-1">
                    {route.edges.map((e) => (
                      <div key={`${e.from}${e.to}`} className="flex items-center justify-between text-xs text-muted">
                        <Mono>{e.from} → {e.to}</Mono><span>quality {Math.round(e.link_quality * 100)}% · {e.recent_failures} failures · cost <b className="text-ink-soft">{e.cost}</b></span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <div className="flex flex-wrap gap-1.5 text-xs">
                <Badge tone="outline">{view.security.encryption ? 'AES-256-GCM on' : 'encryption off'}</Badge>
                <Badge tone="outline">{view.security.signing ? 'Ed25519 signing on' : 'signing off'}</Badge>
              </div>
            </div>
          ) : <Empty icon={WifiOff} title="This node is switched off">Its log is still on disk; it hears nobody and reaches nobody.</Empty>}
        </Card>
        <Card className="overflow-hidden">
          <CardHeader title="Where this phone sits" />
          <div className="p-2"><MeshGraph snapshot={snapshot} selected={nodeId} onSelect={(i) => navigate(`/node/${i}`)} highlight={route ? [{ path: route.path }] : []} height={300} animate={false} /></div>
        </Card>
      </div>
    </div>
  )
}
