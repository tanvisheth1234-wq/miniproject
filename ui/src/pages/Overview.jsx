import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ArrowRight, Boxes, Building2, CheckCircle2, Cpu, Database, FlaskConical, Fingerprint, GitBranch, HardDriveDownload,
  KeyRound, Layers, MapPinned, MessageSquareOff, Network, Radio, Route as RouteIcon, ServerOff, Shield, ShieldCheck,
  Siren, Smartphone, TowerControl, Users, Waypoints,
} from 'lucide-react'
import MeshGraph from '../components/MeshGraph'
import { Badge, Button, Callout, Card, Mono, cx } from '../components/ui'
import { useLab } from '../lib/lab'
import { pct } from '../lib/format'

const fade = { initial: { opacity: 0, y: 16 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, margin: '-60px' }, transition: { duration: 0.5 } }

function Section({ eyebrow, title, children, lead }) {
  return (
    <section className="mt-24">
      <motion.div {...fade} className="mb-9 max-w-3xl">
        <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-crimson-600">{eyebrow}</div>
        <h2 className="font-display text-[30px] font-semibold leading-[1.12] sm:text-[36px]">{title}</h2>
        {lead && <p className="mt-3 text-[15.5px] leading-relaxed text-ink-soft">{lead}</p>}
      </motion.div>
      {children}
    </section>
  )
}

const FAILS = [
  { icon: ServerOff, title: 'They need a server', body: 'WhatsApp, Signal, Telegram and SMS all send your message to a machine far away, then back to the person sitting next to you.' },
  { icon: MessageSquareOff, title: 'One cut breaks everything', body: 'A working Wi-Fi router with a severed uplink is enough to silence every one of them, even though the devices on it can still talk at full speed.' },
  { icon: MapPinned, title: 'Rescuers search blind', body: 'People trapped in a collapsed building cannot signal position or condition, so teams must search room by room.' },
]

const EXITS = [
  { icon: TowerControl, tag: 'Exit 1', title: 'A gateway node', body: 'One person still has a bar of signal. They advertise as a GATEWAY, and routing treats reaching any gateway as reaching the outside. Fifty trapped people share one person’s single bar.', to: '/demo' },
  { icon: Users, tag: 'Exit 2', title: 'A rescue team walks in', body: 'The moment a RESCUE node comes within range of anyone, the whole mesh becomes reachable and every pending SOS flows in, with sender IDs and the path each took.', to: '/rescue' },
  { icon: HardDriveDownload, tag: 'Exit 3', title: 'Store-and-forward', body: 'With no path, a node keeps the message instead of dropping it. When someone carries their phone to a node that has a path, the queue flushes. A person becomes a courier without knowing it.', to: '/reliability' },
]

const LAYERS = [
  { name: 'Interface', mod: 'ui/ · api/server.py', body: 'React node view and rescue dashboard, served with a FastAPI + WebSocket API.', to: '/node', icon: Smartphone },
  { name: 'Node', mod: 'mesh/core/node.py', body: 'Wires every layer together; the one class the API needs.', to: '/demo', icon: Cpu },
  { name: 'Security', mod: 'crypto.py', body: 'AES-256-GCM payloads, Ed25519 signed headers.', to: '/security', icon: Shield },
  { name: 'Reliability', mod: 'reliability.py', body: 'Priority queue, dedup, ACK + retry, bounded store-and-forward.', to: '/reliability', icon: ShieldCheck },
  { name: 'Routing', mod: 'routing.py', body: 'Link-state gossip, weighted cost function, Dijkstra, route cache.', to: '/routing', icon: RouteIcon },
  { name: 'Discovery & relay', mod: 'discovery.py · relay.py', body: 'HELLO broadcast, neighbour table, death detection, hop-by-hop forwarding.', to: '/demo', icon: Waypoints },
  { name: 'Wire protocol', mod: 'packet.py', body: 'A 52-byte header, path, payload, optional signature.', to: '/protocol', icon: Layers },
  { name: 'Transport', mod: 'transport_udp.py · transport_sim.py', body: 'UDP multicast + TCP for real sockets; an in-memory radio for the simulator. Same interface.', to: '/simulator', icon: Radio },
]

const FEATURES = [
  ['Multicast peer discovery with a live neighbour table', 'discovery.py', '/demo'],
  ['Custom binary wire protocol over UDP + TCP', 'packet.py · transport_udp.py', '/protocol'],
  ['Link-state gossip and distributed graph construction', 'routing.py', '/routing'],
  ['Dijkstra over a weighted cost function, not hop count', 'routing.py', '/routing'],
  ['Priority queue; SOS pre-emption re-applied at every hop', 'reliability.py · relay.py', '/reliability'],
  ['TTL, duplicate detection, ACK + retry, heartbeat failure detection', 'reliability.py · discovery.py', '/reliability'],
  ['Node roles: NORMAL, GATEWAY, RESCUE', 'discovery.py · routing.py', '/demo'],
  ['Store-and-forward queue for unroutable messages', 'reliability.py · node.py', '/reliability'],
  ['AES-256-GCM encryption; Ed25519 signed headers', 'crypto.py', '/security'],
  ['Per-node SQLite message and event log', 'store.py', '/reliability'],
  ['Single-process concurrency via asyncio', 'node.py', '/demo'],
  ['Network simulator with injectable loss, latency and failures', 'sim/ · api/lab.py', '/simulator'],
  ['Metrics harness: delivery, hops, latency by priority, recovery', 'api/metrics.py', '/simulator'],
  ['React node UI and rescue dashboard, served by each node', 'ui/ · api/', '/node'],
]

const PHASES = [
  { n: 1, name: 'Problem definition & wire protocol', done: 'Packet format, UDP/TCP transport, two-node demo', who: 'Tanvi · Miti' },
  { n: 2, name: 'SRS, UML & algorithm design', done: 'Discovery, relay, simulator transport; use-case, class, sequence, activity diagrams', who: 'Miti · Group' },
  { n: 3, name: 'Module-wise coding', done: 'Routing, reliability, security, storage, node integration; 256 tests', who: 'Twissha' },
  { n: 4, name: 'Integration, API & interface', done: 'FastAPI + WebSocket, node view, rescue dashboard, simulator with metrics, this website', who: 'Tanvi', current: true },
  { n: 5, name: 'End semester', done: 'Evaluation, report, viva', who: 'Group' },
]

export default function Overview() {
  const { snapshot } = useLab()
  const stats = snapshot?.stats
  return (
    <div>
      {/* ---------------- hero ---------------- */}
      <section className="grid items-center gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
        <div>
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
            <Badge tone="crimson" className="mb-5">TE Sem V Mini Project I · Group 20</Badge>
          </motion.div>
          <motion.h1 initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="font-display text-[44px] font-semibold leading-[1.04] sm:text-[58px]">
            When the towers fall, the phones become <span className="text-crimson-600">the network.</span>
          </motion.h1>
          <motion.p initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 }} className="mt-6 max-w-xl text-[17px] leading-relaxed text-ink-soft">
            EcoMesh is a decentralised disaster-relief mesh. Every device is a walkie-talkie <em>and</em> a relay tower: if your message can’t reach someone directly, it hops
            through other people’s devices until it arrives. No internet, no cell tower, no central server.
          </motion.p>
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="mt-8 flex flex-wrap gap-3">
            <Link to="/demo"><Button variant="primary" size="lg">Run the live demo <ArrowRight size={17} /></Button></Link>
            <Link to="/node"><Button size="lg">Try the SOS button</Button></Link>
            <Link to="/rescue"><Button size="lg" variant="ghost">Rescue dashboard</Button></Link>
          </motion.div>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.35 }} className="mt-10 grid max-w-md grid-cols-3 gap-6 border-t border-line pt-6">
            {[
              [stats ? `${stats.nodes_online}/${stats.nodes_total}` : '—', 'nodes live now'],
              [stats ? pct(stats.delivery_ratio) : '—', 'delivered so far'],
              ['0', 'servers involved'],
            ].map(([v, l]) => (
              <div key={l}><div className="font-display text-3xl font-semibold tabular">{v}</div><div className="mt-1 text-xs text-muted">{l}</div></div>
            ))}
          </motion.div>
        </div>
        <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.15, duration: 0.6 }}>
          <Card className="overflow-hidden shadow-[0_30px_70px_-34px_rgba(63,44,30,0.35)]">
            <div className="flex items-center justify-between border-b border-line px-5 py-3 text-xs text-muted">
              <span className="flex items-center gap-2"><span className="h-2 w-2 animate-pulse rounded-full bg-ok" /> A real mesh, running on this page</span>
              <Link to="/demo" className="font-medium text-crimson-700 hover:underline">Open it →</Link>
            </div>
            <div className="p-2">{snapshot ? <MeshGraph snapshot={snapshot} height={400} /> : <div className="grid h-[400px] place-items-center text-sm text-muted">Starting the mesh…</div>}</div>
          </Card>
        </motion.div>
      </section>

      {/* ---------------- the insight ---------------- */}
      <Section eyebrow="The idea" title="After a disaster, connectivity isn’t zero. It’s patchy."
        lead="Someone near a window has one bar. Someone has a satellite messenger. One access point is still running off a UPS. Normally that helps only the person holding it. We chain devices together so one person’s signal becomes everyone’s.">
        <div className="grid gap-5 md:grid-cols-3">
          {FAILS.map((f, i) => (
            <motion.div key={f.title} {...fade} transition={{ delay: i * 0.08 }}>
              <Card className="h-full p-6">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-crimson-50 text-crimson-600"><f.icon size={20} /></span>
                <h3 className="mt-4 text-base font-semibold">{f.title}</h3>
                <p className="mt-2 text-[14px] leading-relaxed text-muted">{f.body}</p>
              </Card>
            </motion.div>
          ))}
        </div>
      </Section>

      <Section eyebrow="How a message gets out" title="Three exits. All three are built." lead="A message from someone with no signal at all can travel through strangers’ devices until it reaches whoever can get it out.">
        <div className="grid gap-5 md:grid-cols-3">
          {EXITS.map((e, i) => (
            <motion.div key={e.tag} {...fade} transition={{ delay: i * 0.08 }}>
              <Link to={e.to} className="group block h-full">
                <Card className="h-full p-6 transition-all group-hover:-translate-y-0.5 group-hover:border-crimson-200 group-hover:shadow-[0_18px_40px_-24px_rgba(138,33,27,0.35)]">
                  <div className="flex items-center justify-between">
                    <span className="grid h-10 w-10 place-items-center rounded-xl bg-brown-100 text-brown-700"><e.icon size={20} /></span>
                    <Badge tone="brown">{e.tag}</Badge>
                  </div>
                  <h3 className="mt-4 font-display text-xl font-semibold">{e.title}</h3>
                  <p className="mt-2 text-[14px] leading-relaxed text-muted">{e.body}</p>
                  <div className="mt-4 flex items-center gap-1 text-sm font-medium text-crimson-700">See it work <ArrowRight size={14} className="transition-transform group-hover:translate-x-1" /></div>
                </Card>
              </Link>
            </motion.div>
          ))}
        </div>
      </Section>

      {/* ---------------- architecture ---------------- */}
      <Section eyebrow="Architecture" title="Eight layers, one node, no shortcuts"
        lead="Every device runs the same stack. The transport at the bottom is swappable: LAN sockets today, a radio tomorrow, and nothing above it changes.">
        <div className="grid gap-3 lg:grid-cols-2">
          {LAYERS.map((l, i) => (
            <motion.div key={l.name} {...fade} transition={{ delay: (i % 4) * 0.05 }}>
              <Link to={l.to} className="group flex items-center gap-4 rounded-2xl border border-line bg-white px-5 py-4 transition-colors hover:border-crimson-200 hover:bg-crimson-50/30">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-wash-2 text-brown-600 transition-colors group-hover:bg-crimson-50 group-hover:text-crimson-600"><l.icon size={20} /></span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-3"><span className="font-semibold">{l.name}</span><Mono className="text-muted">{l.mod}</Mono></div>
                  <div className="mt-0.5 text-[13px] leading-snug text-muted">{l.body}</div>
                </div>
                <ArrowRight size={16} className="shrink-0 text-line-strong transition-all group-hover:translate-x-1 group-hover:text-crimson-600" />
              </Link>
            </motion.div>
          ))}
        </div>
      </Section>

      {/* ---------------- features ---------------- */}
      <Section eyebrow="Scope" title="Every in-scope feature, with somewhere to see it"
        lead="The project plan commits to fourteen things. Each one links to the page that exercises it against the real engine.">
        <Card className="overflow-hidden">
          <ul>
            {FEATURES.map(([name, mod, to], i) => (
              <li key={name}>
                <Link to={to} className="group flex items-center gap-4 border-b border-line/70 px-5 py-3.5 transition-colors last:border-0 hover:bg-wash">
                  <span className="tabular w-6 text-sm font-semibold text-brown-300">{String(i + 1).padStart(2, '0')}</span>
                  <CheckCircle2 size={17} className="shrink-0 text-ok" />
                  <span className="flex-1 text-[14.5px] font-medium">{name}</span>
                  <Mono className="hidden text-muted md:block">{mod}</Mono>
                  <span className="text-xs font-medium text-crimson-700 opacity-0 transition-opacity group-hover:opacity-100">view →</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      </Section>

      {/* ---------------- phases ---------------- */}
      <Section eyebrow="Project timeline" title="Five phases, one branch each">
        <div className="relative grid gap-4 md:grid-cols-5">
          {PHASES.map((p, i) => (
            <motion.div key={p.n} {...fade} transition={{ delay: i * 0.07 }}>
              <Card className={cx('h-full p-5', p.current && 'border-crimson-300 ring-2 ring-crimson-100')}>
                <div className="flex items-center justify-between">
                  <span className={cx('grid h-8 w-8 place-items-center rounded-full text-sm font-semibold', p.current ? 'bg-crimson-600 text-white' : 'bg-brown-100 text-brown-700')}>{p.n}</span>
                  {p.current ? <Badge tone="crimson">You are here</Badge> : p.n < 4 ? <Badge tone="ok">Done</Badge> : <Badge tone="outline">Next</Badge>}
                </div>
                <h3 className="mt-4 text-sm font-semibold leading-snug">{p.name}</h3>
                <p className="mt-2 text-[13px] leading-relaxed text-muted">{p.done}</p>
                <div className="mt-3 flex items-center gap-1.5 text-xs text-brown-500"><GitBranch size={12} /> {p.who}</div>
              </Card>
            </motion.div>
          ))}
        </div>
      </Section>

      <section className="mt-24">
        <Callout tone="crimson" icon={Fingerprint} title="The honest statement">
          The mesh currently runs over LAN sockets, which stand in for Bluetooth Low Energy or Wi-Fi Direct. On LAN we restrict each node’s visible neighbour set to emulate limited
          radio range. This lets us develop and measure the routing, prioritisation and reliability logic without radio hardware. Discovery, routing, reliability and encryption are
          all transport-agnostic — replacing LAN sockets with a radio transport does not change any layer above it.
          A browser also can’t open raw UDP sockets, so this website is a <em>screen for</em> a node, not a node: the nodes run in the Python engine behind it.
        </Callout>
      </section>

      <section className="mt-24 grid gap-5 md:grid-cols-3">
        {[
          { name: 'Tanvi Sheth', track: 'Track A', role: 'Protocol & networking · Phase 4: API, interface, integration' },
          { name: 'Twissha Shah', track: 'Track B', role: 'Routing & reliability · security, storage, node integration' },
          { name: 'Miti Shah', track: 'Track C', role: 'Platform, data & interface · discovery, relay, simulator' },
        ].map((m) => (
          <Card key={m.name} className="p-6">
            <div className="flex items-center gap-3">
              <span className="grid h-11 w-11 place-items-center rounded-full bg-crimson-600 font-display text-lg font-semibold text-white">{m.name[0]}</span>
              <div><div className="font-semibold">{m.name}</div><div className="text-xs font-medium text-crimson-700">{m.track}</div></div>
            </div>
            <p className="mt-4 text-[13.5px] leading-relaxed text-muted">{m.role}</p>
          </Card>
        ))}
      </section>
    </div>
  )
}
