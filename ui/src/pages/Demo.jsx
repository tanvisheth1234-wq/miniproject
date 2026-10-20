import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  AlertTriangle, ArrowRight, CheckCircle2, CircleDot, Gauge, GitFork, Link2, Lock, Play, Power, PowerOff,
  RotateCcw, Scissors, ShieldAlert, Siren, SquareStack, Zap,
} from 'lucide-react'
import MeshGraph, { GraphLegend } from '../components/MeshGraph'
import { EventFeed, PathChips, RoleBadge, StatStrip } from '../components/parts'
import { Badge, Button, Callout, Card, CardHeader, Field, Mono, PageHeader, Segmented, Select, Toggle, cx } from '../components/ui'
import { api } from '../lib/api'
import { RESCUE_DST } from '../lib/format'
import { useAction, useLab, useLive } from '../lib/lab'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

/** Section 18's six beats. Each `run` drives the real API; nothing is faked. */
function useBeats(snapshot) {
  const sender = snapshot?.config?.sender || 'L1'
  const gateway = snapshot?.nodes?.find((n) => n.role === 'GATEWAY')?.id
  const [done, setDone] = useState({})
  const [note, setNote] = useState({})
  const [running, setRunning] = useState(null)
  const victim = useRef(null)

  const finish = (n, text) => { setDone((d) => ({ ...d, [n]: true })); setNote((x) => ({ ...x, [n]: text })) }

  const beats = [
    {
      n: 1, title: 'Self-organisation',
      body: 'Nobody typed an address. Every node broadcast HELLOs, learned its neighbours, and gossiped link-state until all of them hold the whole map.',
      cta: 'Check convergence',
      run: async () => {
        const snap = await api.get('/api/lab')
        const total = snap.nodes.length
        const known = snap.nodes.filter((n) => n.online).map((n) => n.known_nodes)
        const ok = known.every((k) => k === total)
        finish(1, ok ? `All ${total} nodes know all ${total} nodes — no configuration was entered.` : `Still converging: nodes know ${known.join(', ')} of ${total}. Give it a few seconds.`)
      },
    },
    {
      n: 2, title: 'Priority',
      body: 'Pile routine traffic up behind a slow radio, then raise an SOS after it. Every hop’s queue picks priority before arrival order, so the SOS still arrives first.',
      cta: `Send 6 routine + 1 SOS from ${sender}`,
      run: async () => {
        const r = await api.post('/api/lab/burst', { src: sender, dst: RESCUE_DST, normal: 6, service_ms: 150 })
        await sleep(6500)
        const msgs = await Promise.all([r.sos, ...r.normal].map((id) => api.get(`/api/messages/${id}`)))
        const arrivals = msgs.map((m, i) => ({ sos: i === 0, t: m.latency_ms })).filter((a) => a.t != null).sort((a, b) => a.t - b.t)
        const rank = arrivals.findIndex((a) => a.sos) + 1
        finish(2, rank ? `The SOS arrived ${rank === 1 ? 'first' : `#${rank}`} of ${arrivals.length}, though it was sent last.` : 'Messages are still in flight — check the Reliability page for arrival order.')
      },
    },
    {
      n: 3, title: 'Self-healing',
      body: 'Switch off the relay the SOS route is using. Neighbours notice the silence, the graph redraws, and the next message goes around.',
      cta: 'Kill the relay on the active path',
      run: async () => {
        const route = await api.get(`/api/nodes/${sender}/route?dst=${RESCUE_DST}`)
        const path = route.weighted?.path ?? []
        const relay = path.length > 2 ? path[1] : null
        if (!relay) return finish(3, 'No relay on the current path to take out — the sender is already next to a gateway.')
        victim.current = relay
        await api.post(`/api/lab/nodes/${relay}/kill`)
        await sleep(snapshot?.config?.timing?.neighbour_timeout ? snapshot.config.timing.neighbour_timeout * 1000 + 1500 : 5000)
        const sent = await api.post(`/api/nodes/${sender}/sos`, { text: `SOS from ${sender} — sent after ${relay} died` })
        await sleep(3500)
        const detail = await api.get(`/api/messages/${sent.msg_id}`)
        finish(3, detail.arrived ? `${relay} is down. The new SOS still arrived via ${detail.route.join(' → ')}.` : `${relay} is down; the message is still working its way through (status: ${detail.origin.status}).`)
      },
    },
    {
      n: 4, title: 'No path',
      body: 'Switch off the gateway, then send five SOS messages. With nowhere to go they are held in store-and-forward — not dropped.',
      cta: 'Kill the gateway, send 5 SOS',
      run: async () => {
        if (!gateway) return finish(4, 'This preset has no gateway.')
        await api.post(`/api/lab/nodes/${gateway}/kill`)
        await sleep((snapshot?.config?.timing?.neighbour_timeout ?? 3) * 1000 + 1500)
        for (let i = 1; i <= 5; i++) {
          await api.post(`/api/nodes/${sender}/sos`, { text: `SOS ${i} of 5 from ${sender} — gateway is down` }).catch(() => {})
          await sleep(250)
        }
        await sleep(1500)
        const view = await api.get(`/api/nodes/${sender}`)
        finish(4, `${view.queues.store_forward.length} SOS messages are being held at ${sender}, undelivered but not lost.`)
      },
    },
    {
      n: 5, title: 'The flush',
      body: 'Bring the gateway back. Discovery finds it, routes reappear, and every held SOS goes out at once. This is the moment the panel remembers.',
      cta: 'Bring the gateway back',
      run: async () => {
        if (!gateway) return finish(5, 'This preset has no gateway.')
        const before = (await api.get(`/api/nodes/${sender}`)).queues.store_forward.length
        await api.post(`/api/lab/nodes/${gateway}/revive`)
        await sleep(9000)
        const after = (await api.get(`/api/nodes/${sender}`)).queues.store_forward.length
        finish(5, `${before - after} of ${before} held messages flushed through the returning gateway.`)
      },
    },
    {
      n: 6, title: 'Scale and evidence',
      body: 'Leave the live mesh for the simulator: dozens of nodes, packet loss, scripted failures, and the metrics table.',
      cta: 'Open the simulator',
      run: async () => { window.location.assign('/simulator') },
    },
  ]
  return { beats, done, note, running, setRunning, reset: () => { setDone({}); setNote({}) } }
}

function NodeInspector({ nodeId, snapshot, onClose }) {
  const node = snapshot.nodes.find((n) => n.id === nodeId)
  const { data: view } = useLive(nodeId ? `/api/nodes/${nodeId}` : null)
  const toggle = useAction(async () => api.post(`/api/lab/nodes/${nodeId}/${node.online ? 'kill' : 'revive'}`))
  const sos = useAction(async () => api.post(`/api/nodes/${nodeId}/sos`))
  if (!node) return null
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <div className="flex items-center gap-3">
          <Mono className="rounded-md bg-brown-800 px-2 py-1 text-sm font-semibold text-white">{node.id}</Mono>
          <div>
            <div className="text-sm font-semibold">{node.label}</div>
            <div className="mt-0.5 flex items-center gap-2"><RoleBadge role={node.role} /><span className="text-xs text-muted">{node.online ? 'online' : 'switched off'}</span></div>
          </div>
        </div>
        <button onClick={onClose} className="text-xs text-muted hover:text-ink">Close</button>
      </div>
      <div className="grid grid-cols-3 divide-x divide-line border-b border-line text-center">
        {[['Nearby', node.neighbours.length], ['Knows', `${node.known_nodes}/${snapshot.nodes.length}`], ['Held', node.store_forward]].map(([k, v]) => (
          <div key={k} className="py-3"><div className="font-display text-xl font-semibold tabular">{v}</div><div className="text-[11px] uppercase tracking-wider text-muted">{k}</div></div>
        ))}
      </div>
      <div className="flex flex-wrap gap-2 p-4">
        <Button variant={node.online ? 'danger' : 'dark'} size="sm" icon={node.online ? PowerOff : Power} busy={toggle.busy} onClick={toggle.run}>
          {node.online ? 'Switch off' : 'Switch on'}
        </Button>
        <Button variant="primary" size="sm" icon={Siren} disabled={!node.online} busy={sos.busy} onClick={sos.run}>Raise SOS</Button>
        <a href={`/node/${node.id}`} className="inline-flex h-8 items-center rounded-xl px-3 text-[13px] font-medium text-crimson-700 hover:bg-crimson-50">Open node view <ArrowRight size={13} className="ml-1" /></a>
      </div>
      {(toggle.error || sos.error) && <div className="px-5 pb-3 text-xs text-crimson-600">{toggle.error || sos.error}</div>}
      {view?.online && (
        <div className="border-t border-line px-5 py-4">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">Best route to rescue</div>
          {view.rescue_route ? <PathChips path={view.rescue_route.path} /> : <div className="text-sm text-crimson-600">No route — SOS would be held.</div>}
          {view.rescue_route && <div className="mt-2 text-xs text-muted">{view.rescue_route.hops} hops · cost {view.rescue_route.cost}</div>}
        </div>
      )}
    </Card>
  )
}

function Controls({ snapshot }) {
  const cfg = snapshot.config
  const [presets, setPresets] = useState([])
  useEffect(() => { api.get('/api/presets').then(setPresets).catch(() => {}) }, [])
  const reset = useAction(async (body) => api.post('/api/lab/reset', body))
  const [draft, setDraft] = useState(null)
  const d = draft ?? { preset: cfg.preset, encryption: cfg.encryption, signing: cfg.signing, routing: cfg.routing }
  const set = (patch) => setDraft({ ...d, ...patch })
  const dirty = draft && (d.preset !== cfg.preset || d.encryption !== cfg.encryption || d.signing !== cfg.signing || d.routing !== cfg.routing)
  const radio = useAction(async (v) => api.patch('/api/lab/config', { radio_service_ms: v }))
  return (
    <Card>
      <CardHeader icon={SquareStack} title="The mesh" subtitle="Real nodes, one process, simulated radio." />
      <div className="space-y-4 p-5">
        <Field label="Layout">
          <Select value={d.preset} onChange={(e) => set({ preset: e.target.value })}>
            {presets.map((p) => <option key={p.id} value={p.id}>{p.title} · {p.nodes} nodes</option>)}
          </Select>
          <span className="mt-1.5 block text-xs leading-snug text-muted">{presets.find((p) => p.id === d.preset)?.summary}</span>
        </Field>
        <Toggle checked={d.encryption} onChange={(v) => set({ encryption: v })} label="Encrypt payloads" hint="AES-256-GCM. Relays carry ciphertext only." />
        <Toggle checked={d.signing} onChange={(v) => set({ signing: v })} label="Sign headers" hint="Ed25519, keys distributed in HELLO." />
        <div>
          <div className="mb-1.5 text-sm font-medium">Routing</div>
          <Segmented size="sm" value={d.routing} onChange={(v) => set({ routing: v })} options={[{ value: 'weighted', label: 'Weighted (Dijkstra)' }, { value: 'hopcount', label: 'Hop count' }]} />
        </div>
        <div className="flex items-center gap-2">
          <Button variant="primary" icon={RotateCcw} busy={reset.busy} disabled={!dirty && !!snapshot} onClick={async () => { await reset.run(d); setDraft(null) }}>Apply &amp; restart mesh</Button>
          <Button variant="ghost" onClick={() => reset.run({ preset: cfg.preset, encryption: cfg.encryption, signing: cfg.signing, routing: cfg.routing }).then(() => setDraft(null))}>Restart</Button>
        </div>
        {reset.error && <div className="text-xs text-crimson-600">{reset.error}</div>}
        <div className="border-t border-line pt-4">
          <div className="mb-1.5 flex items-center justify-between text-sm font-medium">Radio capacity <Badge tone="outline">{cfg.radio_service_ms ? `1 pkt / ${cfg.radio_service_ms} ms` : 'unlimited'}</Badge></div>
          <input type="range" min="0" max="400" step="20" value={cfg.radio_service_ms} onChange={(e) => radio.run(Number(e.target.value))} className="w-full accent-crimson-600" aria-label="Radio capacity" />
          <p className="mt-1 text-xs leading-snug text-muted">Slow the radio down and queues form, so priority has something to reorder.</p>
        </div>
      </div>
    </Card>
  )
}

function Beats({ snapshot }) {
  const { beats, done, note, running, setRunning, reset } = useBeats(snapshot)
  return (
    <Card>
      <CardHeader icon={Play} title="Guided demo" subtitle="The six beats from the project plan. Each button drives the real engine."
        action={<Button variant="ghost" size="sm" onClick={reset}>Clear</Button>} />
      <ol className="divide-y divide-line">
        {beats.map((b) => (
          <li key={b.n} className="px-5 py-4">
            <div className="flex items-start gap-3">
              <span className={cx('mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-semibold', done[b.n] ? 'bg-ok text-white' : 'bg-brown-100 text-brown-700')}>
                {done[b.n] ? <CheckCircle2 size={14} /> : b.n}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold">{b.title}</div>
                <p className="mt-1 text-[13px] leading-relaxed text-muted">{b.body}</p>
                <AnimatePresence>
                  {note[b.n] && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="mt-2 overflow-hidden rounded-lg bg-ok-bg px-3 py-2 text-[13px] font-medium text-ok">{note[b.n]}</motion.div>
                  )}
                </AnimatePresence>
                <Button className="mt-3" size="sm" variant={b.n === 5 || b.n === 2 ? 'primary' : 'outline'} busy={running === b.n} disabled={running != null && running !== b.n}
                  onClick={async () => { setRunning(b.n); try { await b.run() } catch (e) { alert(e.message) } finally { setRunning(null) } }}>
                  {b.cta}
                </Button>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </Card>
  )
}

function LinkEditor({ snapshot }) {
  const ids = snapshot.nodes.map((n) => n.id)
  const [a, setA] = useState(ids[0])
  const [b, setB] = useState(ids[1] ?? ids[0])
  const [loss, setLoss] = useState(0)
  const save = useAction(async () => api.put('/api/lab/links', { a, b, loss }))
  const cut = useAction(async () => api.del(`/api/lab/links/${a}/${b}`))
  useEffect(() => { if (!ids.includes(a)) setA(ids[0]); if (!ids.includes(b)) setB(ids[1] ?? ids[0]) }, [ids.join(',')]) // eslint-disable-line
  const exists = snapshot.links.find((l) => (l.a === a && l.b === b) || (l.a === b && l.b === a))
  useEffect(() => { if (exists) setLoss(exists.loss) }, [exists?.loss, a, b]) // eslint-disable-line
  return (
    <Card>
      <CardHeader icon={Link2} title="Links" subtitle="Who can hear whom. Add, degrade or cut a link and watch routes adapt." />
      <div className="space-y-4 p-5">
        <div className="grid grid-cols-2 gap-3">
          <Field label="From"><Select value={a} onChange={(e) => setA(e.target.value)}>{ids.map((i) => <option key={i}>{i}</option>)}</Select></Field>
          <Field label="To"><Select value={b} onChange={(e) => setB(e.target.value)}>{ids.map((i) => <option key={i}>{i}</option>)}</Select></Field>
        </div>
        <Field label={`Packet loss · ${Math.round(loss * 100)}%`}>
          <input type="range" min="0" max="0.8" step="0.05" value={loss} onChange={(e) => setLoss(Number(e.target.value))} className="w-full accent-crimson-600" />
        </Field>
        <div className="flex gap-2">
          <Button variant="dark" size="sm" busy={save.busy} disabled={a === b} onClick={save.run}>{exists ? 'Update link' : 'Create link'}</Button>
          <Button variant="danger" size="sm" icon={Scissors} busy={cut.busy} disabled={!exists} onClick={cut.run}>Cut link</Button>
        </div>
        {(save.error || cut.error) && <div className="text-xs text-crimson-600">{save.error || cut.error}</div>}
      </div>
    </Card>
  )
}

export default function Demo() {
  const { snapshot, events, actions, connected } = useLab()
  const [selected, setSelected] = useState(null)
  const [view, setView] = useState('all')

  const highlight = useMemo(() => [], [])
  if (!snapshot) {
    return <div className="py-24 text-center text-muted">{connected ? 'Loading the mesh…' : 'Waiting for the EcoMesh server on port 8000…'}</div>
  }
  return (
    <div>
      <PageHeader eyebrow="Live demo" title="A real mesh, running right now"
        actions={<Badge tone="outline">{snapshot.config.title} · {snapshot.nodes.length} nodes · {snapshot.config.routing === 'weighted' ? 'weighted routing' : 'hop-count routing'}</Badge>}>
        Every circle is a real <Mono>Node</Mono> from the Python engine: discovery, link-state gossip, Dijkstra, ACK and retry, store-and-forward, SQLite log.
        Click one to inspect it, switch it off, or raise an SOS. Drag to rearrange.
      </PageHeader>

      <StatStrip stats={snapshot.stats} />

      <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-6">
          <Card className="overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3.5">
              <div className="flex items-center gap-2 text-[15px] font-semibold"><CircleDot size={16} className="text-crimson-600" /> Topology</div>
              <GraphLegend />
            </div>
            <div className="bg-white p-2"><MeshGraph snapshot={snapshot} selected={selected} onSelect={setSelected} highlight={highlight} height={470} /></div>
          </Card>

          <AnimatePresence>
            {selected && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                <NodeInspector nodeId={selected} snapshot={snapshot} onClose={() => setSelected(null)} />
              </motion.div>
            )}
          </AnimatePresence>

          <EventFeed events={events} height={340} />

          {actions.length > 0 && (
            <Card>
              <CardHeader title="Operator log" subtitle="What was done to the mesh, newest first." />
              <ul className="max-h-48 divide-y divide-line/70 overflow-y-auto">
                {[...actions].reverse().slice(0, 25).map((a, i) => (
                  <li key={i} className="flex items-center gap-3 px-5 py-2 text-[13px] text-ink-soft">
                    <Mono className="text-muted">{new Date(a.ts_ms).toLocaleTimeString([], { hour12: false })}</Mono>{a.text}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        <div className="space-y-6">
          <Beats snapshot={snapshot} />
          <Controls snapshot={snapshot} />
          <LinkEditor snapshot={snapshot} />
        </div>
      </div>
    </div>
  )
}
