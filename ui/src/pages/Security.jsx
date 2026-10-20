import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Check, Eye, FileKey2, KeyRound, Lock, PenLine, ShieldAlert, ShieldCheck, Swords, X } from 'lucide-react'
import { Badge, Button, Callout, Card, CardHeader, Field, Input, Mono, PageHeader, Segmented, cx } from '../components/ui'
import { api } from '../lib/api'
import { useAction } from '../lib/lab'

const Hex = ({ children, tone }) => (
  <Mono className={cx('block break-all rounded-lg px-3 py-2 leading-relaxed', tone === 'crimson' ? 'bg-crimson-50 text-crimson-700' : tone === 'ok' ? 'bg-ok-bg text-ok' : 'bg-wash text-ink-soft')}>{children}</Mono>
)

function Encryption() {
  const [text, setText] = useState('Four of us in room 302. One unconscious.')
  const [sealed, setSealed] = useState(null)
  const [opened, setOpened] = useState(null)
  const seal = useAction(async () => { setOpened(null); const out = await api.post('/api/security/seal', { text }); setSealed(out); return out })
  const open = useAction(async (tamper) => { const out = await api.post('/api/security/open', { wire: sealed.wire, tamper }); setOpened(out); return out })
  return (
    <Card>
      <CardHeader icon={Lock} title="Confidentiality and integrity · AES-256-GCM" subtitle="Relays read the header, never the payload. A relay that changes even one bit is caught." />
      <div className="space-y-4 p-5">
        <Field label="Message"><Input value={text} onChange={(e) => setText(e.target.value)} maxLength={200} /></Field>
        <Button variant="dark" onClick={seal.run} busy={seal.busy}><Lock size={15} /> Encrypt</Button>
        {sealed && (
          <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
            <div><div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">What a relay carries · {sealed.wire_bytes} bytes</div><Hex tone="crimson">{sealed.nonce}<span className="text-muted">·</span>{sealed.ciphertext}<span className="text-muted">·</span>{sealed.tag}</Hex>
              <div className="mt-1 flex gap-3 text-[11px] text-muted"><span>12-byte nonce</span><span>{sealed.plaintext_bytes}-byte ciphertext</span><span>16-byte GCM tag</span></div></div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => open.run(false)} busy={open.busy}><Eye size={14} /> Decrypt at the destination</Button>
              <Button size="sm" variant="danger" onClick={() => open.run(true)} busy={open.busy}><ShieldAlert size={14} /> A relay flips one bit, then decrypt</Button>
            </div>
            <AnimatePresence mode="wait">
              {opened && (
                <motion.div key={String(opened.ok) + opened.tampered} initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} className={cx('flex items-start gap-3 rounded-xl px-4 py-3 text-sm', opened.ok ? 'bg-ok-bg text-ok' : 'bg-crimson-50 text-crimson-700')}>
                  {opened.ok ? <Check size={18} className="mt-0.5" /> : <X size={18} className="mt-0.5" />}
                  <div>{opened.ok ? <>Decrypted: <b>“{opened.plaintext}”</b></> : <><b>Rejected.</b> {opened.error}. The GCM tag no longer matches, so the destination drops it rather than show corrupted text.</>}</div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        )}
      </div>
    </Card>
  )
}

function Signing() {
  const [msg, setMsg] = useState('SOS from L1: trapped, second floor')
  const [who, setWho] = useState('alice')
  const [signed, setSigned] = useState(null)
  const [check, setCheck] = useState(null)
  const sign = useAction(async () => { setCheck(null); const out = await api.post('/api/security/sign', { message: msg, who }); setSigned(out); return out })
  const verify = useAction(async (message, label) => {
    const out = await api.post('/api/security/verify', { message, public_key: signed.public_key, signature: signed.signature })
    setCheck({ ...out, label, message })
    return out
  })
  return (
    <Card>
      <CardHeader icon={PenLine} title="Authenticity · Ed25519" subtitle="Proves a message came from the node named in `src`, so a relay can’t forge an SOS." />
      <div className="space-y-4 p-5">
        <Field label="Message to sign"><Input value={msg} onChange={(e) => setMsg(e.target.value)} maxLength={200} /></Field>
        <div className="flex flex-wrap items-center gap-3">
          <Segmented size="sm" value={who} onChange={setWho} options={[{ value: 'alice', label: 'Sign as Alice (honest)' }, { value: 'mallory', label: 'Sign as Mallory (forger)' }]} />
          <Button variant="dark" onClick={sign.run} busy={sign.busy}><KeyRound size={15} /> Sign</Button>
        </div>
        {signed && (
          <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
            <div><div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">Signer’s public key (distributed in HELLO)</div><Hex>{signed.public_key}</Hex></div>
            <div><div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">64-byte signature</div><Hex tone="ok">{signed.signature}</Hex></div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => verify.run(signed.message, 'the original message')} busy={verify.busy}>Verify the original</Button>
              <Button size="sm" variant="danger" onClick={() => verify.run(signed.message + '!', 'a message altered by one character')} busy={verify.busy}>Verify an altered copy</Button>
            </div>
            {check && <div className={cx('flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium', check.valid ? 'bg-ok-bg text-ok' : 'bg-crimson-50 text-crimson-700')}>{check.valid ? <Check size={17} /> : <X size={17} />} {check.valid ? 'Signature valid for' : 'Signature INVALID for'} {check.label}.</div>}
            {who === 'mallory' && <p className="text-xs text-muted">Mallory can sign anything, but only with <i>her</i> key. A destination holding Alice’s real public key will not accept it as Alice’s.</p>}
          </motion.div>
        )}
      </div>
    </Card>
  )
}

function Drill() {
  const [result, setResult] = useState(null)
  const run = useAction(async () => { setResult(null); const out = await api.post('/api/security/drill'); setResult(out); return out })
  return (
    <Card>
      <CardHeader icon={Swords} title="Attack drill on a live mesh" subtitle="A — M — B, with M hostile. Real nodes and packets; the verdicts come from B's own event log."
        action={<Button variant="primary" size="sm" busy={run.busy} onClick={run.run}>Run the drill</Button>} />
      <div className="p-5">
        {!result && !run.busy && (
          <ol className="space-y-2 text-[13.5px] leading-relaxed text-muted">
            <li><b className="text-ink-soft">1. Honest relay.</b> M forwards A’s message untouched.</li>
            <li><b className="text-ink-soft">2. Tampered ciphertext.</b> M flips a bit; only the AES-GCM tag can notice.</li>
            <li><b className="text-ink-soft">3. Same, but signed.</b> The signature covers the ciphertext, so it fails even earlier.</li>
            <li><b className="text-ink-soft">4. Forged SOS.</b> M signs “SOS from A” with M’s own private key.</li>
          </ol>
        )}
        {run.busy && <div className="py-8 text-center text-sm text-muted">Starting three nodes, letting them find each other, attacking…</div>}
        {run.error && <div className="text-sm text-crimson-600">{run.error}</div>}
        {result && (
          <div className="space-y-3">
            {result.steps.map((s, i) => (
              <motion.div key={s.title} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.18 }} className={cx('flex items-start gap-4 rounded-xl border px-4 py-3.5', s.defended ? 'border-ok/30 bg-ok-bg/40' : 'border-crimson-300 bg-crimson-50')}>
                <span className={cx('mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full text-white', s.defended ? 'bg-ok' : 'bg-crimson-600')}>{s.defended ? <ShieldCheck size={15} /> : <ShieldAlert size={15} />}</span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2"><span className="text-sm font-semibold">{s.title}</span>{s.mechanism && <Badge tone="outline">{s.mechanism}</Badge>}</div>
                  <div className="mt-0.5 text-[13px] text-muted">{s.what}</div>
                  <div className={cx('mt-1.5 text-[13px] font-medium', s.defended ? 'text-ok' : 'text-crimson-700')}>{s.verdict}{s.delivered.length > 0 && <> — “{s.delivered[0]}”</>}</div>
                </div>
              </motion.div>
            ))}
            <Callout tone="brown" icon={ShieldAlert} title="Known limit">{result.note}</Callout>
          </div>
        )}
      </div>
    </Card>
  )
}

export default function Security() {
  return (
    <div>
      <PageHeader eyebrow="Security" title="Strangers carry the message. They can’t read it, change it, or forge one.">
        Messages transit devices belonging to people you’ve never met. Confidentiality and tamper detection come from AES-256-GCM; sender authenticity from Ed25519.
        Both use the vetted <Mono>cryptography</Mono> library — nothing here is hand-rolled, which is the correct engineering answer, not a weakness.
        To run the whole live mesh encrypted and signed, switch both on in the <a className="font-medium text-crimson-700 hover:underline" href="/demo">Live demo</a> controls.
      </PageHeader>
      <div className="grid gap-6 xl:grid-cols-2">
        <Encryption />
        <Signing />
      </div>
      <div className="mt-6"><Drill /></div>
      <Card className="mt-6">
        <CardHeader icon={FileKey2} title="Threat model" />
        <div className="overflow-x-auto"><table className="w-full text-left text-[13.5px]">
          <thead><tr className="border-b border-line bg-wash text-[11px] uppercase tracking-wider text-muted"><th className="px-5 py-2.5">Concern</th><th className="px-5 py-2.5">Mechanism</th><th className="px-5 py-2.5">Status in this build</th></tr></thead>
          <tbody className="text-ink-soft">
            {[
              ['Confidentiality', 'Payload encrypted with AES-256-GCM; relays read the header only', 'Built · opt-in'],
              ['Integrity / tamper detection', 'GCM authentication tag; a relay modifying the payload is detected at the destination', 'Built · opt-in'],
              ['Forged SOS / Sybil resistance', 'Ed25519 over identity fields; public keys travel in HELLO and in link-state reports', 'Built · opt-in'],
              ['Key establishment', 'Phase 1: pre-shared session key. Later: X25519 agreement per node pair', 'Pre-shared key (documented upgrade path)'],
            ].map(([a, b, c]) => <tr key={a} className="border-b border-line/70 last:border-0"><td className="px-5 py-3 font-medium text-ink">{a}</td><td className="px-5 py-3">{b}</td><td className="px-5 py-3"><Badge tone="ok">{c}</Badge></td></tr>)}
          </tbody>
        </table></div>
      </Card>
    </div>
  )
}
