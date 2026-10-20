import { useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { BarChart3, CheckCircle2, FlaskConical, Play, Target, Timer, XCircle } from 'lucide-react'
import { Badge, Button, Callout, Card, CardHeader, Empty, Field, Input, Mono, PageHeader, Select, cx } from '../components/ui'
import { api } from '../lib/api'
import { ms, num, pct } from '../lib/format'
import { useAction } from '../lib/lab'

/** Section 16's targets, as checks over an aggregated summary. */
function targets(s, scenario) {
  const rows = []
  if (s.delivery_ratio) rows.push({ k: 'Delivery ratio', v: pct(s.delivery_ratio.mean, 1), t: '≥ 90 %', ok: s.delivery_ratio.mean >= 0.9, note: `min ${pct(s.delivery_ratio.min)} · max ${pct(s.delivery_ratio.max)}` })
  if (s.median_hops != null) rows.push({ k: 'Median relays', v: num(s.median_hops, 0), t: 'report distribution', ok: null, note: `mean ${num(s.mean_hops, 2)}` })
  if (s.sos_latency_advantage) rows.push({ k: 'SOS latency advantage', v: `${num(s.sos_latency_advantage, 1)}×`, t: '≥ 3× faster', ok: s.sos_latency_advantage >= 3, note: `SOS ${ms(s.latency_ms.SOS)} vs routine ${ms(s.latency_ms.NORMAL)}` })
  if (s.recovery_s) rows.push({ k: 'Recovery after relay death', v: `${num(s.recovery_s.mean, 1)} s`, t: '≤ 10 s', ok: s.recovery_s.mean <= 10, note: `worst ${num(s.recovery_s.max, 1)} s` })
  if (s.convergence_s) rows.push({ k: 'Convergence', v: `${num(s.convergence_s.mean, 1)} s`, t: '≤ 15 s', ok: s.convergence_s.mean <= 15, note: `worst ${num(s.convergence_s.max, 1)} s` })
  if (s.store_forward.queued) rows.push({ k: 'Store-and-forward flush', v: pct(s.store_forward.flush_ratio, 0), t: '100 %', ok: s.store_forward.flush_ratio >= 0.999, note: `${s.store_forward.flushed} of ${s.store_forward.queued} held packets` })
  if (s.dedup_drop_ratio != null) rows.push({ k: 'Dedup drops', v: pct(s.dedup_drop_ratio, 1), t: 'report', ok: null, note: 'duplicates ÷ packets received' })
  return rows
}

function Histogram({ data }) {
  const entries = Object.entries(data).map(([k, v]) => [Number(k), v])
  if (!entries.length) return <div className="py-6 text-center text-sm text-muted">No deliveries.</div>
  const max = Math.max(...entries.map(([, v]) => v))
  const lo = Math.min(...entries.map(([k]) => k))
  const hi = Math.max(...entries.map(([k]) => k))
  const bins = Array.from({ length: hi - lo + 1 }, (_, i) => [lo + i, data[lo + i] ?? 0])
  return (
    <div className="flex h-44 items-end gap-2">
      {bins.map(([h, n], i) => (
        <div key={h} className="flex h-full flex-1 flex-col items-center justify-end gap-1.5">
          <span className="tabular text-[11px] text-muted">{n || ''}</span>
          <motion.div className="w-full max-w-[44px] rounded-t-md bg-crimson-500" initial={{ height: 0 }} animate={{ height: `${(n / max) * 100}%` }} transition={{ duration: 0.6, delay: i * 0.04 }} style={{ minHeight: n ? 3 : 0 }} />
          <span className="tabular text-xs font-medium text-ink-soft">{h}</span>
        </div>
      ))}
    </div>
  )
}

function RunBars({ runs, color }) {
  return (
    <div className="flex h-28 items-end gap-1">
      {runs.map((r, i) => (
        <motion.div key={r.seed} className={cx('flex-1 rounded-t', color)} title={`seed ${r.seed}: ${pct(r.delivery_ratio)} (${r.delivered}/${r.sent})`}
          initial={{ height: 0 }} animate={{ height: `${Math.max(2, (r.delivery_ratio ?? 0) * 100)}%` }} transition={{ delay: i * 0.02 }} />
      ))}
    </div>
  )
}

function Summary({ title, s, scenario, tone }) {
  const rows = targets(s, scenario)
  return (
    <Card>
      <CardHeader title={title} subtitle={`${s.runs} runs · ${num(s.wall_s, 1)} s of CPU for ${s.runs} simulated mesh lifetimes`} />
      <div className="divide-y divide-line/70">
        {rows.map((r) => (
          <div key={r.k} className="grid grid-cols-[1fr_auto] items-center gap-4 px-5 py-3.5">
            <div><div className="text-sm font-medium">{r.k}</div><div className="text-xs text-muted">{r.note}</div></div>
            <div className="flex items-center gap-3 text-right">
              <div><div className={cx('tabular font-display text-2xl font-semibold', r.ok === false ? 'text-crimson-600' : r.ok ? 'text-ok' : 'text-ink')}>{r.v}</div><div className="text-[11px] uppercase tracking-wider text-muted">target {r.t}</div></div>
              {r.ok === true ? <CheckCircle2 size={18} className="text-ok" /> : r.ok === false ? <XCircle size={18} className="text-crimson-500" /> : <span className="w-[18px]" />}
            </div>
          </div>
        ))}
      </div>
      <div className="border-t border-line p-5">
        <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">Relays per delivered message</div>
        <Histogram data={s.hop_histogram} />
      </div>
    </Card>
  )
}

export default function Simulator() {
  const [scenarios, setScenarios] = useState([])
  const [id, setId] = useState('hopcount_vs_weighted')
  const [runs, setRuns] = useState(6)
  const [nodes, setNodes] = useState('')
  const [loss, setLoss] = useState('')
  const [job, setJob] = useState(null)
  const timer = useRef()

  useEffect(() => { api.get('/api/sim/scenarios').then(setScenarios).catch(() => {}) }, [])
  const sc = scenarios.find((s) => s.id === id)

  const start = useAction(async () => {
    clearTimeout(timer.current)
    const body = { scenario: id, runs, seed: 1 }
    if (nodes) body.nodes = Number(nodes)
    if (loss !== '') body.loss = Number(loss)
    const j = await api.post('/api/sim/run', body)
    setJob(j)
    const poll = async () => {
      const next = await api.get(`/api/sim/jobs/${j.id}`)
      setJob(next)
      if (next.status === 'running') timer.current = setTimeout(poll, 500)
    }
    timer.current = setTimeout(poll, 400)
  })
  useEffect(() => () => clearTimeout(timer.current), [])

  const done = job?.status === 'done'
  const weighted = job?.summary?.weighted
  const hop = job?.summary?.hopcount
  const lift = weighted && hop ? weighted.delivery_ratio.mean - hop.delivery_ratio.mean : null

  return (
    <div>
      <PageHeader eyebrow="Simulator & evaluation" title="Forty nodes, 20% loss, and the numbers to prove it">
        The same <Mono>Node</Mono> class, wired to an in-memory radio instead of sockets, running on a <b>virtual clock</b>: the spec’s real 3 s HELLO, 10 s timeout and 4 s ACK values play out in
        milliseconds of wall time, so a whole evaluation takes seconds. Every figure is a query against the nodes’ SQLite logs.
      </PageHeader>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
        <div className="space-y-6">
          <Card>
            <CardHeader icon={FlaskConical} title="Scenario" subtitle="The six required by the plan, plus the priority claim." />
            <div className="space-y-4 p-5">
              <div className="space-y-1.5">
                {scenarios.map((s) => (
                  <button key={s.id} onClick={() => setId(s.id)} className={cx('w-full rounded-xl border px-4 py-3 text-left transition-colors', id === s.id ? 'border-crimson-300 bg-crimson-50/60' : 'border-line hover:bg-wash')}>
                    <div className="flex items-center justify-between"><span className="text-sm font-semibold">{s.title}</span><Mono className="text-muted">{s.nodes}n · {Math.round(s.loss * 100)}%</Mono></div>
                    {id === s.id && <p className="mt-1.5 text-[13px] leading-snug text-muted">{s.summary}</p>}
                    {id === s.id && s.events.length > 0 && <div className="mt-2 flex flex-wrap gap-1.5">{s.events.map((e) => <Badge key={e} tone="brown" className="normal-case tracking-normal">{e}</Badge>)}</div>}
                  </button>
                ))}
              </div>
              <div className="grid grid-cols-3 gap-3">
                <Field label="Runs"><Input type="number" min={1} max={300} value={runs} onChange={(e) => setRuns(Number(e.target.value))} /></Field>
                <Field label="Nodes"><Input type="number" min={4} max={60} placeholder={sc?.nodes} value={nodes} onChange={(e) => setNodes(e.target.value)} /></Field>
                <Field label="Loss"><Input type="number" min={0} max={0.6} step={0.05} placeholder={sc?.loss} value={loss} onChange={(e) => setLoss(e.target.value)} /></Field>
              </div>
              <Button variant="primary" size="lg" className="w-full" icon={Play} busy={start.busy || job?.status === 'running'} onClick={start.run}>Run {runs} simulation{runs === 1 ? '' : 's'}</Button>
              {start.error && <div className="text-xs text-crimson-600">{start.error}</div>}
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          {!job && <Card><Empty icon={BarChart3} title="Pick a scenario and run it">Results appear here: delivery ratio, hop distribution, latency by priority, recovery time — each checked against its target.</Empty></Card>}

          {job?.status === 'running' && (
            <Card className="p-6">
              <div className="mb-2 flex justify-between text-sm"><span className="font-medium">{job.title}</span><span className="tabular text-muted">{job.completed}/{job.total} runs</span></div>
              <div className="h-2.5 overflow-hidden rounded-full bg-wash-2"><motion.div className="h-full bg-crimson-600" animate={{ width: `${(job.completed / job.total) * 100}%` }} /></div>
              <p className="mt-3 text-xs text-muted">Each run builds a fresh mesh, lets it converge, plays the failure script and tallies the logs. They run in parallel worker processes, so the live lab stays responsive.</p>
            </Card>
          )}
          {job?.status === 'error' && <Callout tone="crimson" title="The simulation failed">{job.error}</Callout>}

          {done && job.modes.length === 2 && (
            <Card className="overflow-hidden border-crimson-200">
              <div className="grid divide-line sm:grid-cols-[1fr_auto_1fr] sm:divide-x">
                <div className="p-6"><div className="text-xs font-semibold uppercase tracking-wider text-muted">Hop-count routing</div><div className="tabular mt-1 font-display text-5xl font-semibold text-brown-400">{pct(hop.delivery_ratio.mean)}</div><div className="mt-1 text-sm text-muted">delivered</div><div className="mt-4"><RunBars runs={job.per_run.filter((r) => r.mode === 'hopcount')} color="bg-brown-300" /></div></div>
                <div className="grid place-items-center px-6 py-4 text-center"><div><div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Weighted wins by</div><div className="tabular font-display text-4xl font-semibold text-crimson-600">+{Math.round(lift * 100)} pts</div></div></div>
                <div className="p-6"><div className="text-xs font-semibold uppercase tracking-wider text-crimson-600">Weighted (Dijkstra)</div><div className="tabular mt-1 font-display text-5xl font-semibold text-crimson-600">{pct(weighted.delivery_ratio.mean)}</div><div className="mt-1 text-sm text-muted">delivered</div><div className="mt-4"><RunBars runs={job.per_run.filter((r) => r.mode === 'weighted')} color="bg-crimson-500" /></div></div>
              </div>
              <div className="border-t border-line bg-wash px-6 py-3 text-[13px] text-muted">Identical topology, seeds and traffic; messages are best-effort (no ACK, no retry) so a bad route choice shows up directly as lost messages. The short path crosses a lossy link; the router with real link-quality costs takes the longer clean one.</div>
            </Card>
          )}

          {done && (
            <div className={cx('grid gap-6', job.modes.length === 1 ? '' : '2xl:grid-cols-2')}>
              {job.modes.map((m) => <Summary key={m} s={job.summary[m]} scenario={job.scenario} title={m === 'weighted' ? (job.modes.length === 2 ? 'Weighted routing · full table' : `${job.title} · ${job.nodes_in_mesh} nodes`) : 'Hop-count routing · full table'} />)}
            </div>
          )}

          {done && job.modes.length === 1 && (
            <Card>
              <CardHeader icon={BarChart3} title="Delivery ratio per run" subtitle="One bar per simulated lifetime (different seed each)." />
              <div className="p-5"><RunBars runs={job.per_run} color="bg-crimson-500" /></div>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
