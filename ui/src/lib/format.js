// Small, pure helpers shared by every page.

export const PRIORITY = {
  0: { name: 'SOS', tone: 'sos' },
  1: { name: 'NORMAL', tone: 'normal' },
  2: { name: 'STATUS', tone: 'status' },
}

export const ROLE_LABEL = { NORMAL: 'Survivor', GATEWAY: 'Gateway', RESCUE: 'Rescue' }

export const RESCUE_DST = 'RESCUE__'

export function pct(value, digits = 0) {
  if (value == null || Number.isNaN(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export function num(value, digits = 1) {
  if (value == null || Number.isNaN(value)) return '—'
  return Number(value).toFixed(digits)
}

export function ms(value) {
  if (value == null) return '—'
  if (value >= 10000) return `${(value / 1000).toFixed(0)} s`
  if (value >= 1000) return `${(value / 1000).toFixed(1)} s`
  return `${Math.round(value)} ms`
}

export function ago(createdMs, now = Date.now()) {
  const s = Math.max(0, Math.round((now - createdMs) / 1000))
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  return `${m}m ${s % 60}s ago`
}

export function clock(tsMs) {
  const d = new Date(tsMs)
  return d.toLocaleTimeString([], { hour12: false }) + '.' + String(d.getMilliseconds()).padStart(3, '0')
}

export function shortId(id) {
  return id ? id.slice(0, 8) : ''
}

/** Human wording for what a node's message is doing right now. */
export function describeStatus(m) {
  const relays = m.relays?.length ?? 0
  if (m.direction === 'received') {
    return { key: 'received', label: relays ? `Received · relayed via ${relays} node${relays === 1 ? '' : 's'}` : 'Received · direct' }
  }
  switch (m.status) {
    case 'delivered':
      return {
        key: 'delivered',
        label: m.hop_count == null ? 'Delivered' : m.hop_count === 0 ? 'Delivered · direct' : `Delivered · relayed via ${m.hop_count} node${m.hop_count === 1 ? '' : 's'}`,
      }
    case 'queued_sf':
      return { key: 'queued', label: 'Held for later · no route right now' }
    case 'failed':
      return { key: 'failed', label: 'Failed' }
    default:
      return { key: 'sending', label: 'Sending · waiting for acknowledgement' }
  }
}

export const EVENT_LABEL = {
  sent: 'sent',
  recv: 'received',
  forward: 'relayed',
  ack: 'acknowledged',
  retry: 'retry',
  sf_queue: 'held (store-and-forward)',
  sf_flush: 'flushed',
  peer_up: 'peer joined',
  peer_down: 'peer lost',
  route_change: 'route recomputed',
  drop_dup: 'duplicate dropped',
  drop_ttl: 'TTL expired',
  drop_loop: 'loop dropped',
  drop_no_route: 'no route',
  drop_send_failed: 'send failed',
  drop_decrypt_failed: 'decrypt failed',
  drop_signature_invalid: 'bad signature',
  drop_unknown_signer: 'unknown signer',
  lost_on_crash: 'lost in crash',
  evicted: 'evicted',
  expired: 'expired',
}

export function eventTone(kind) {
  if (kind.startsWith('drop_') || kind === 'lost_on_crash' || kind === 'peer_down' || kind === 'evicted' || kind === 'expired') return 'bad'
  if (kind === 'recv' || kind === 'ack' || kind === 'sf_flush' || kind === 'peer_up') return 'good'
  if (kind === 'retry' || kind === 'sf_queue') return 'warn'
  return 'neutral'
}
