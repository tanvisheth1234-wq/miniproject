import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { ArrowDown, Binary, Copy, Layers, Shuffle } from 'lucide-react'
import { HexView } from '../components/parts'
import { Badge, Button, Callout, Card, CardHeader, Field, Input, Mono, PageHeader, Segmented, Select, Table, Textarea, Toggle, cx } from '../components/ui'
import { api } from '../lib/api'
import { useAction } from '../lib/lab'

const REGION_LEGEND = [
  ['header', 'bg-brown-100 text-brown-800', '52-byte header'],
  ['path', 'bg-warn-bg text-warn', 'relay path'],
  ['payload', 'bg-crimson-50 text-crimson-700', 'payload'],
  ['signature', 'bg-ok-bg text-ok', 'Ed25519 signature'],
]

function Inspector({ packet, title = 'Packet' }) {
  const [active, setActive] = useState(null)
  if (!packet) return null
  return (
    <div className="space-y-5">
      <div>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm font-semibold">{title} · <span className="tabular text-muted">{packet.length} bytes</span></div>
          <div className="flex flex-wrap gap-1.5">{REGION_LEGEND.filter(([n]) => packet.regions.some((r) => r.name === n)).map(([n, c, l]) => <span key={n} className={cx('rounded px-2 py-0.5 text-[11px] font-medium', c)}>{l}</span>)}</div>
        </div>
        <HexView hex={packet.hex} regions={packet.regions} fields={packet.fields} active={active} onActive={setActive} />
      </div>
      <div className="overflow-hidden rounded-xl border border-line">
        <table className="w-full text-[13px]">
          <thead><tr className="border-b border-line bg-wash text-left text-[11px] uppercase tracking-wider text-muted">
            <th className="px-3 py-2">Offset</th><th className="px-3 py-2">Field</th><th className="px-3 py-2">Bytes</th><th className="px-3 py-2">Value</th><th className="hidden px-3 py-2 lg:table-cell">What it does</th>
          </tr></thead>
          <tbody>
            {packet.fields.map((f) => (
              <tr key={f.name} onMouseEnter={() => setActive(f.name)} onMouseLeave={() => setActive(null)}
                  className={cx('border-b border-line/70 last:border-0', active === f.name && 'bg-crimson-50')}>
                <td className="tabular px-3 py-2 text-muted">{f.offset}</td>
                <td className="px-3 py-2 font-mono font-semibold">{f.name}</td>
                <td className="px-3 py-2 font-mono text-xs text-muted">{f.hex.length > 18 ? f.hex.slice(0, 18) + '…' : f.hex}</td>
                <td className="px-3 py-2 font-medium text-ink">{f.value}</td>
                <td className="hidden px-3 py-2 text-xs text-muted lg:table-cell">{f.meaning}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {packet.path.length > 0 && <div className="text-[13px]"><b>Path</b> <Mono className="text-muted">{packet.path.join(' → ')}</Mono></div>}
      {packet.payload_hex && (
        <div className="text-[13px]">
          <b>Payload</b>{' '}
          {packet.payload_text != null
            ? <span className="rounded bg-crimson-50 px-2 py-0.5 text-crimson-700">“{packet.payload_text}” <span className="text-muted">(plaintext on the wire)</span></span>
            : <Mono className="break-all text-muted">{packet.payload_hex.slice(0, 96)}{packet.payload_hex.length > 96 ? '…' : ''} <span className="font-sans text-crimson-700">(ciphertext: 12-byte nonce, then data, then 16-byte GCM tag)</span></Mono>}
        </div>
      )}
    </div>
  )
}

function Builder({ onBuilt }) {
  const [form, setForm] = useState({ type: 'DATA', priority: 0, src: 'L1', dst: 'RESCUE__', ttl: 10, hop_count: 0, path: '', text: 'trapped in room 302, two injured', needs_ack: true, store_forward_ok: true, encrypt: false, sign: false })
  const set = (patch) => setForm((f) => ({ ...f, ...patch }))
  const build = useAction(async (f) => {
    const out = await api.post('/api/protocol/build', { ...f, path: f.path.split(',').map((s) => s.trim()).filter(Boolean) })
    onBuilt(out)
    return out
  })
  useEffect(() => { build.run(form) }, [form]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Card>
      <CardHeader icon={Binary} title="Packet builder" subtitle="Change a field and the real encoder re-packs it." />
      <div className="space-y-4 p-5">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Type"><Select value={form.type} onChange={(e) => set({ type: e.target.value })}>{['DATA', 'ACK', 'HELLO', 'LINK_STATE'].map((t) => <option key={t}>{t}</option>)}</Select></Field>
          <Field label="Priority"><Select value={form.priority} onChange={(e) => set({ priority: Number(e.target.value) })}><option value={0}>0 · SOS</option><option value={1}>1 · NORMAL</option><option value={2}>2 · STATUS</option></Select></Field>
          <Field label="Source"><Input value={form.src} maxLength={8} onChange={(e) => set({ src: e.target.value })} /></Field>
          <Field label="Destination"><Input value={form.dst} maxLength={8} onChange={(e) => set({ dst: e.target.value })} /></Field>
          <Field label="TTL"><Input type="number" min={0} max={255} value={form.ttl} onChange={(e) => set({ ttl: Number(e.target.value) })} /></Field>
          <Field label="Hop count"><Input type="number" min={0} max={255} value={form.hop_count} onChange={(e) => set({ hop_count: Number(e.target.value) })} /></Field>
        </div>
        <Field label="Relay path" hint="Comma-separated node ids, e.g. L1, L2"><Input value={form.path} onChange={(e) => set({ path: e.target.value })} placeholder="(empty: no relays yet)" /></Field>
        <Field label="Payload"><Textarea value={form.text} onChange={(e) => set({ text: e.target.value })} /></Field>
        <div className="grid gap-3">
          <Toggle label="Needs ACK" checked={form.needs_ack} onChange={(v) => set({ needs_ack: v })} />
          <Toggle label="Store-and-forward OK" checked={form.store_forward_ok} onChange={(v) => set({ store_forward_ok: v })} />
          <Toggle label="Encrypt (AES-256-GCM)" checked={form.encrypt} onChange={(v) => set({ encrypt: v })} />
          <Toggle label="Sign (Ed25519)" checked={form.sign} onChange={(v) => set({ sign: v })} />
        </div>
        {build.error && <div className="rounded-lg bg-crimson-50 px-3 py-2 text-xs text-crimson-700">{build.error}</div>}
      </div>
    </Card>
  )
}

function RelayDemo({ packet }) {
  const [relay, setRelay] = useState('L2')
  const step = useAction(async () => api.post('/api/protocol/relay', { hex: packet.hex, relay }))
  const [result, setResult] = useState(null)
  useEffect(() => { setResult(null) }, [packet?.hex])
  const run = async () => { const r = await step.run(); if (r) setResult(r) }
  const diff = result && ['ttl', 'hop_count'].map((k) => [k, result.before.summary[k], result.after.summary[k]])
  return (
    <Card>
      <CardHeader icon={Shuffle} title="What a relay does" subtitle="It reads the header and rewrites three fields. The payload is never touched." />
      <div className="space-y-4 p-5">
        <div className="flex items-end gap-3">
          <Field label="Relay node id"><Input value={relay} maxLength={8} onChange={(e) => setRelay(e.target.value)} /></Field>
          <Button variant="dark" onClick={run} busy={step.busy}>Forward the packet above</Button>
        </div>
        {step.error && <div className="rounded-lg bg-crimson-50 px-3 py-2 text-xs text-crimson-700">{step.error}</div>}
        {result && (
          <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="grid gap-3 sm:grid-cols-3">
            {diff.map(([k, a, b]) => (
              <div key={k} className="rounded-xl bg-wash p-3 text-center"><div className="text-[11px] uppercase tracking-wider text-muted">{k}</div><div className="mt-1 font-display text-2xl font-semibold"><span className="text-muted line-through decoration-1">{a}</span> <span className="text-crimson-600">{b}</span></div></div>
            ))}
            <div className="rounded-xl bg-wash p-3 text-center"><div className="text-[11px] uppercase tracking-wider text-muted">path</div><div className="mt-1 font-mono text-sm font-semibold text-crimson-700">+ {relay}</div></div>
            <div className="rounded-xl bg-ok-bg p-3 text-center sm:col-span-3 text-sm font-medium text-ok">payload bytes identical before and after: {result.before.payload_hex === result.after.payload_hex ? 'yes' : 'NO'}</div>
          </motion.div>
        )}
      </div>
    </Card>
  )
}

function Parser() {
  const [hex, setHex] = useState('')
  const [parsed, setParsed] = useState(null)
  const parse = useAction(async () => { const out = await api.post('/api/protocol/parse', { hex }); setParsed(out); return out })
  return (
    <Card>
      <CardHeader icon={Layers} title="Decode raw bytes" subtitle="Paste a hex dump from the two-node demo (or anywhere) and the real parser reads it back." />
      <div className="space-y-3 p-5">
        <Textarea value={hex} onChange={(e) => setHex(e.target.value)} placeholder="4d45 0102 …" className="font-mono !text-xs" spellCheck={false} />
        <div className="flex items-center gap-3"><Button variant="dark" onClick={parse.run} busy={parse.busy} disabled={!hex.trim()}>Parse</Button>{parse.error && <span className="text-xs text-crimson-600">{parse.error}</span>}</div>
        {parsed && <div className="border-t border-line pt-4"><Inspector packet={parsed} title="Parsed" /></div>}
      </div>
    </Card>
  )
}

export default function Protocol() {
  const [packet, setPacket] = useState(null)
  return (
    <div>
      <PageHeader eyebrow="Wire protocol" title="52 bytes that every node agrees on">
        A custom binary format, network byte order throughout. Relays need <Mono>dst</Mono>, <Mono>ttl</Mono> and <Mono>priority</Mono> from the header, so those stay in the clear;
        the payload is opaque bytes. Hover a byte to see which field it belongs to. This page runs the same <Mono>Packet.pack()</Mono> the nodes use.
      </PageHeader>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
        <Builder onBuilt={setPacket} />
        <div className="space-y-6">
          <Card className="p-5"><Inspector packet={packet} title="Packed packet" /></Card>
          {packet && <RelayDemo packet={packet} />}
        </div>
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <Parser />
        <Card>
          <CardHeader title="Why a custom format?" />
          <div className="space-y-4 p-5 text-[14px] leading-relaxed text-ink-soft">
            <p><b>Fixed-size header.</b> A stream transport can read exactly 52 bytes, ask the header how much more is coming (<Mono>payload_len</Mono>, <Mono>path_len</Mono>, the signed flag) and read that — no length prefix needed.</p>
            <p><b>One field is rewritten per hop.</b> <Mono>ttl</Mono> goes down, <Mono>hop_count</Mono> goes up, and the relay appends itself to the path. The path doubles as loop detection: seeing your own id means the packet has been round once already.</p>
            <p><b>Signatures cover identity, not hops.</b> Because those three fields change at every relay, an Ed25519 signature over them could only ever verify at the first hop. The signature covers type, priority, flags, ids, timestamp and payload instead, so it survives the whole journey.</p>
            <p><b>The last byte is a retransmission counter.</b> It was reserved in the spec; we now use it so a relay can tell a sender’s retry from a duplicate copy.</p>
          </div>
        </Card>
      </div>
    </div>
  )
}
