import { motion } from 'framer-motion'
import { Loader2 } from 'lucide-react'
import { PRIORITY } from '../lib/format'

export const cx = (...parts) => parts.filter(Boolean).join(' ')

export function Card({ className, children, ...rest }) {
  return (
    <div className={cx('rounded-2xl border border-line bg-white', className)} {...rest}>
      {children}
    </div>
  )
}

export function CardHeader({ title, subtitle, action, icon: Icon }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
      <div className="flex items-start gap-3">
        {Icon && (
          <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-crimson-50 text-crimson-600">
            <Icon size={17} strokeWidth={2} />
          </span>
        )}
        <div>
          <h3 className="text-[15px] font-semibold leading-tight text-ink">{title}</h3>
          {subtitle && <p className="mt-1 text-[13px] leading-snug text-muted">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  )
}

const BUTTON = {
  primary: 'bg-crimson-600 text-white hover:bg-crimson-700 active:bg-crimson-800 disabled:bg-crimson-200',
  dark: 'bg-brown-800 text-white hover:bg-brown-700 disabled:bg-brown-300',
  outline: 'border border-line-strong bg-white text-ink hover:bg-wash disabled:text-muted/60',
  ghost: 'text-ink-soft hover:bg-wash-2 disabled:text-muted/60',
  danger: 'border border-crimson-200 bg-white text-crimson-700 hover:bg-crimson-50 disabled:text-crimson-200',
}
const BUTTON_SIZE = { sm: 'h-8 px-3 text-[13px] gap-1.5', md: 'h-10 px-4 text-sm gap-2', lg: 'h-12 px-6 text-[15px] gap-2' }

export function Button({ variant = 'outline', size = 'md', busy, icon: Icon, className, children, ...rest }) {
  return (
    <button
      className={cx(
        'inline-flex shrink-0 items-center justify-center rounded-xl font-medium transition-colors disabled:cursor-not-allowed',
        BUTTON[variant], BUTTON_SIZE[size], className,
      )}
      disabled={busy || rest.disabled}
      {...rest}
    >
      {busy ? <Loader2 size={15} className="animate-spin" /> : Icon ? <Icon size={size === 'sm' ? 14 : 16} /> : null}
      {children}
    </button>
  )
}

const TONES = {
  neutral: 'bg-wash-2 text-ink-soft',
  crimson: 'bg-crimson-50 text-crimson-700',
  brown: 'bg-brown-100 text-brown-700',
  ok: 'bg-ok-bg text-ok',
  warn: 'bg-warn-bg text-warn',
  dark: 'bg-brown-800 text-white',
  outline: 'border border-line-strong text-ink-soft',
}

export function Badge({ tone = 'neutral', className, children }) {
  return (
    <span className={cx('inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide', TONES[tone], className)}>
      {children}
    </span>
  )
}

export function PriorityBadge({ priority }) {
  const p = PRIORITY[priority] ?? PRIORITY[1]
  const tone = priority === 0 ? 'crimson' : priority === 1 ? 'brown' : 'neutral'
  return <Badge tone={tone}>{p.name}</Badge>
}

const STATUS_STYLE = {
  sending: { tone: 'warn', dot: 'bg-warn' },
  delivered: { tone: 'ok', dot: 'bg-ok' },
  received: { tone: 'ok', dot: 'bg-ok' },
  queued: { tone: 'warn', dot: 'bg-warn' },
  failed: { tone: 'crimson', dot: 'bg-crimson-500' },
}

export function StatusPill({ status, children }) {
  const s = STATUS_STYLE[status] ?? STATUS_STYLE.sending
  return (
    <span className={cx('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium', TONES[s.tone])}>
      <span className={cx('h-1.5 w-1.5 rounded-full', s.dot, status === 'sending' && 'animate-pulse')} />
      {children}
    </span>
  )
}

export function Stat({ label, value, hint, tone = 'ink', big }) {
  const color = tone === 'crimson' ? 'text-crimson-600' : tone === 'ok' ? 'text-ok' : 'text-ink'
  return (
    <div className="min-w-0">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">{label}</div>
      <motion.div
        key={String(value)}
        initial={{ opacity: 0.4, y: 3 }}
        animate={{ opacity: 1, y: 0 }}
        className={cx('tabular mt-1 font-display font-semibold leading-none', big ? 'text-4xl' : 'text-[28px]', color)}
      >
        {value}
      </motion.div>
      {hint && <div className="mt-1.5 text-xs text-muted">{hint}</div>}
    </div>
  )
}

export function Segmented({ value, onChange, options, size = 'md' }) {
  return (
    <div className="inline-flex rounded-xl border border-line bg-wash p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            'rounded-[10px] font-medium transition-colors',
            size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3.5 py-1.5 text-[13px]',
            value === o.value ? 'bg-white text-crimson-700 shadow-sm ring-1 ring-line' : 'text-muted hover:text-ink',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Toggle({ checked, onChange, label, hint, disabled }) {
  return (
    <label className={cx('flex cursor-pointer items-start justify-between gap-4', disabled && 'opacity-50')}>
      <span>
        <span className="block text-sm font-medium text-ink">{label}</span>
        {hint && <span className="mt-0.5 block text-xs leading-snug text-muted">{hint}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cx('relative mt-0.5 h-6 w-10 shrink-0 rounded-full transition-colors', checked ? 'bg-crimson-600' : 'bg-line-strong')}
      >
        <span className={cx('absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all', checked ? 'left-[18px]' : 'left-0.5')} />
      </button>
    </label>
  )
}

export function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  )
}

const INPUT = 'w-full rounded-xl border border-line-strong bg-white px-3 text-sm text-ink placeholder:text-muted/70 focus:border-crimson-500 focus:outline-none focus:ring-2 focus:ring-crimson-100'
export const Input = (props) => <input className={cx(INPUT, 'h-10', props.className)} {...props} />
export const Select = ({ children, className, ...rest }) => (
  <select className={cx(INPUT, 'h-10 pr-8', className)} {...rest}>{children}</select>
)
export const Textarea = (props) => <textarea className={cx(INPUT, 'min-h-[84px] py-2.5', props.className)} {...props} />

export function Callout({ tone = 'brown', title, children, icon: Icon }) {
  const style = tone === 'crimson' ? 'border-crimson-200 bg-crimson-50/60' : tone === 'ok' ? 'border-ok/30 bg-ok-bg' : 'border-brown-200 bg-brown-50'
  return (
    <div className={cx('flex gap-3 rounded-xl border px-4 py-3.5 text-sm leading-relaxed text-ink-soft', style)}>
      {Icon && <Icon size={18} className="mt-0.5 shrink-0 text-brown-600" />}
      <div>
        {title && <div className="mb-0.5 font-semibold text-ink">{title}</div>}
        {children}
      </div>
    </div>
  )
}

export function Empty({ icon: Icon, title, children }) {
  return (
    <div className="grid place-items-center px-6 py-10 text-center">
      {Icon && <Icon size={26} className="mb-3 text-brown-300" strokeWidth={1.6} />}
      <div className="text-sm font-medium text-ink-soft">{title}</div>
      {children && <div className="mt-1 max-w-sm text-[13px] leading-snug text-muted">{children}</div>}
    </div>
  )
}

export function Mono({ children, className }) {
  return <span className={cx('font-mono text-[12.5px]', className)}>{children}</span>
}

export function PageHeader({ eyebrow, title, children, actions }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-6">
      <div className="max-w-3xl">
        {eyebrow && <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-crimson-600">{eyebrow}</div>}
        <h1 className="font-display text-[34px] font-semibold leading-[1.1] text-ink sm:text-[40px]">{title}</h1>
        {children && <p className="mt-3 text-[15px] leading-relaxed text-ink-soft">{children}</p>}
      </div>
      {actions}
    </div>
  )
}

export function Table({ columns, rows, empty, rowKey, onRowClick, activeKey }) {
  if (!rows.length) return empty ?? null
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[13px]">
        <thead>
          <tr className="border-b border-line bg-wash text-[11px] uppercase tracking-wider text-muted">
            {columns.map((c) => (
              <th key={c.key} className={cx('px-4 py-2.5 font-semibold', c.className)}>{c.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = rowKey(row)
            return (
              <tr
                key={key}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={cx(
                  'border-b border-line/70 last:border-0',
                  onRowClick && 'cursor-pointer hover:bg-wash',
                  activeKey === key && 'bg-crimson-50/50',
                )}
              >
                {columns.map((c) => (
                  <td key={c.key} className={cx('px-4 py-3 align-middle text-ink-soft', c.className)}>{c.render(row)}</td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
