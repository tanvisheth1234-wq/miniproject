import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { Activity, Calculator, GitCompareArrows, Network, TrendingDown } from 'lucide-react'
import MeshGraph from '../components/MeshGraph'
import { PathChips } from '../components/parts'
import { Badge, Button, Callout, Card, CardHeader, Empty, Field, Mono, PageHeader, Select, Table, cx } from '../components/ui'
import { api } from '../lib/api'
import { RESCUE_DST } from '../lib/format'
import { useAction, useLab, useLive } from '../lib/lab'

const edgeCost = (q, f) => 1 + (1 - q) * 5 + f * 3

function CostCalculator() {
  const [q, setQ] = useState(0.55)
  const [f, setF] = useState(0)
  const cost = edgeCost(q, f)
  return (
    <Card>
      <CardHeader icon={Calculator} title="The cost function" subtitle="Section 8.2: edge weight is not 1. Fewest hops is often the flakiest route." />
      <div className="p-5">
        <div className="rounded-xl bg-wash px-4 py-4 font-mono text-[13px] leading-7 text-ink-soft">
          <div><span className="text-brown-500">cost(link)</span> = <b className="text-ink">1</b> <span className="text-muted">// base hop penalty</span></div>
          <div className="pl-[4.2rem]">+ (1 − <span className="text-crimson-600">link_quality</span>) × 5 <span className="text-muted">// weak links are expensive</span></div>
          <div className="pl-[4.2rem]">+ <span className="text-crimson-600">recent_failures</span> × 3 <span className="text-muted">// links that dropped packets are punished</span></div>
        </div>
        <div className="mt-5 grid gap-5 sm:grid-cols-2">
          <Field label={`link_quality · ${(q * 100).toFixed(0)}%`} hint="Fraction of the last 20 expected HELLOs that arrived.">
            <input type="range" min="0" max="1" step="0.01" value={q} onChange={(e) => setQ(Number(e.target.value))} className="w-full accent-crimson-600" />
          </Field>
          <Field label={`recent_failures · ${f}`} hint="ACK timeouts blamed on this link in the last 60 s.">
            <input type="range" min="0" max="6" step="1" value={f} onChange={(e) => setF(Number(e.target.value))} className="w-full accent-crimson-600" />
          </Field>
        </div>
        <div className="mt-5 flex items-end gap-8 border-t border-line pt-5">
          <div><div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Weighted cost</div><motion.div key={cost.toFixed(2)} initial={{ opacity: 0.4, y: 4 }} animate={{ opacity: 1, y: 0 }} className="tabular font-display text-5xl font-semibold text-crimson-600">{cost.toFixed(2)}</motion.div></div>
          <div><div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Hop count says</div><div className="tabular font-display text-5xl font-semibold text-brown-300">1</div></div>
          <p className="max-w-xs pb-1 text-[13px] leading-snug text-muted">At this setting one weak hop costs as much as {Math.max(1, Math.round(cost))} perfect ones, so the router will happily take a longer, cleaner path.</p>
        </div>
      </div>
    </Card>
  )
}

function RouteTable({ title, route, tone }) {
  if (!route) return (
    <div className="rounded-xl border border-dashed border-line-strong p-4 text-sm text-muted"><b className="text-ink-soft">{title}</b>: no route.</div>
  )
  return (
    <div className={cx('rounded-xl border p-4', tone === 'crimson' ? 'border-crimson-200 bg-crimson-50/40' : 'border-brown-200 bg-brown-50/60')}>
      <div className="mb-2 flex items-center justify-between"><b className="text-sm">{title}</b><span className="text-xs text-muted">{route.hops} hops</span></div>
      <PathChips path={route.path} tone={tone} />
      <div className="mt-3 space-y-1">
        {route.edges.map((e) => (
          <div key={e.from + e.to} className="flex items-center justify-between text-xs text-muted">
            <Mono>{e.from} → {e.to}</Mono>
            <span>q {Math.round(e.link_quality * 100)}% · f {e.recent_failures} · <b className="text-ink-soft">{e.cost.toFixed(2)}</b></span>
          </div>
        ))}
      </div>
      <div className="mt-3 border-t border-line pt-2 text-right text-sm">total cost <b className="tabular font-display text-lg">{(route.weighted_cost ?? route.cost).toFixed(2)}</b></div>
    </div>
  )
}

export default function Routing() {
  const { snapshot, connected } = useLab()
  const online = useMemo(() => (snapshot?.nodes ?? []).filter((n) => n.online), [snapshot])
  const [src, setSrc] = useState(null)
  const [dst, setDst] = useState(RESCUE_DST)
  useEffect(() => { if (snapshot && (!src || !online.some((n) => n.id === src))) setSrc(snapshot.config.sender || online[0]?.id) }, [snapshot]) // eslint-disable-line
  const path = src ? `/api/nodes/${src}/route?dst=${encodeURIComponent(dst)}` : null
  const { data: cmp, error } = useLive(path, { every: 900 })
  const { data: graph } = useLive(src ? `/api/nodes/${src}/graph` : null, { every: 1500 })
  const degrade = useAction(async (a, b) => api.put('/api/lab/links', { a, b, loss: 0.5 }))
  const restore = useAction(async (a, b) => api.put('/api/lab/links', { a, b, loss: 0 }))

  if (!snapshot) return <div className="py-24 text-center text-muted">{connected ? 'Loading…' : 'Waiting for the EcoMesh server…'}</div>
  const highlight = cmp ? [cmp.weighted && { path: cmp.weighted.path, tone: 'crimson' }, cmp.hop_count && !cmp.same_path && { path: cmp.hop_count.path, tone: 'brown' }].filter(Boolean) : []
  const firstHop = cmp?.weighted?.path?.length > 2 ? [cmp.weighted.path[1], cmp.weighted.path[2]] : cmp?.weighted?.path?.slice(0, 2)
  const worse = cmp && !cmp.same_path && cmp.weighted && cmp.hop_count ? cmp.hop_count.weighted_cost - cmp.weighted.cost : 0

  return (
    <div>
      <PageHeader eyebrow="Routing" title="Link-state gossip, then Dijkstra over real link quality">
        Each node tells its neighbours who it can hear and how well; the reports are re-flooded until every node holds the whole map (within about 15 seconds).
        A message then takes the <em>cheapest</em> path, not the shortest. Everything below is read from the running engine.
      </PageHeader>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <Card className="overflow-hidden">
          <CardHeader icon={GitCompareArrows} title="Route explorer" subtitle="Pick a node and a destination. Crimson is what the router chooses; brown is what plain hop-count would choose."
            action={cmp && <Badge tone={cmp.same_path ? 'neutral' : 'crimson'}>{cmp.same_path ? 'both agree' : 'they differ'}</Badge>} />
          <div className="grid gap-3 border-b border-line p-5 sm:grid-cols-2">
            <Field label="From"><Select value={src ?? ''} onChange={(e) => setSrc(e.target.value)}>{online.map((n) => <option key={n.id} value={n.id}>{n.id} · {n.label}</option>)}</Select></Field>
            <Field label="To"><Select value={dst} onChange={(e) => setDst(e.target.value)}>
              <option value={RESCUE_DST}>Rescue (any gateway or rescue node)</option>
              {snapshot.nodes.filter((n) => n.id !== src).map((n) => <option key={n.id} value={n.id}>{n.id} · {n.label}</option>)}
            </Select></Field>
          </div>
          <div className="p-2"><MeshGraph snapshot={snapshot} highlight={highlight} selected={src} onSelect={setSrc} height={380} animate={false} /></div>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader icon={Network} title="Chosen path" subtitle={error ? error.message : `From ${src ?? '…'} to ${dst === RESCUE_DST ? 'rescue' : dst}.`} />
            <div className="space-y-3 p-5">
              {cmp ? (
                <>
                  <RouteTable title="Weighted (what EcoMesh uses)" route={cmp.weighted} tone="crimson" />
                  {!cmp.same_path && <RouteTable title="Plain hop-count would pick" route={cmp.hop_count} tone="brown" />}
                  {cmp.same_path && <p className="text-[13px] text-muted">Hop-count routing would choose the very same path here. Degrade a link below and watch them part ways.</p>}
                  {worse > 0.05 && <Callout tone="crimson" icon={TrendingDown}>Hop-count’s path would cost <b>{worse.toFixed(2)}</b> more under the real cost function — it’s the shorter route over a worse link.</Callout>}
                </>
              ) : <Empty icon={Network} title="No route">Nothing in the graph reaches that destination yet.</Empty>}
            </div>
          </Card>

          {firstHop?.length === 2 && (
            <Card>
              <CardHeader icon={Activity} title="Try it" subtitle={`Make ${firstHop[0]} ⇄ ${firstHop[1]} lossy and watch the router move off it. Link quality is measured from HELLO arrival, so allow ~10–20 s.`} />
              <div className="flex flex-wrap gap-2 p-5">
                <Button variant="danger" size="sm" busy={degrade.busy} onClick={() => degrade.run(firstHop[0], firstHop[1])}>Drop 50% of packets on {firstHop[0]} ⇄ {firstHop[1]}</Button>
                <Button variant="outline" size="sm" busy={restore.busy} onClick={() => restore.run(firstHop[0], firstHop[1])}>Restore the link</Button>
              </div>
              {(degrade.error || restore.error) && <div className="px-5 pb-4 text-xs text-crimson-600">{degrade.error || restore.error}</div>}
            </Card>
          )}
        </div>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <CostCalculator />
        <Card>
          <CardHeader icon={Network} title={`What ${src ?? 'this node'} believes`}
            subtitle="Its own copy of the mesh, assembled purely from gossip. Directed edges, with measured quality and cost."
            action={graph && <Badge tone={graph.nodes.length === snapshot.nodes.length ? 'ok' : 'warn'}>knows {graph.nodes.length}/{snapshot.nodes.length}</Badge>} />
          <div className="max-h-[420px] overflow-y-auto">
            <Table
              rowKey={(e) => e.from + e.to}
              rows={graph?.edges ?? []}
              empty={<Empty title="Graph is empty" />}
              columns={[
                { key: 'e', header: 'Edge', render: (e) => <Mono className="font-semibold">{e.from} → {e.to}</Mono> },
                { key: 'q', header: 'Quality', className: 'text-right', render: (e) => <span className="tabular">{Math.round(e.link_quality * 100)}%</span> },
                { key: 'f', header: 'Fail', className: 'text-right', render: (e) => <span className="tabular">{e.recent_failures}</span> },
                { key: 'c', header: 'Cost', className: 'text-right', render: (e) => <b className="tabular text-ink">{e.cost.toFixed(2)}</b> },
              ]}
            />
          </div>
        </Card>
      </div>
    </div>
  )
}
