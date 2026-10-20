import { useEffect, useState } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { ChevronDown, Menu, X } from 'lucide-react'
import { useLab } from './lib/lab'
import { cx } from './components/ui'
import Logo from './components/Logo'
import Overview from './pages/Overview'
import Demo from './pages/Demo'
import NodeView from './pages/NodeView'
import Rescue from './pages/Rescue'
import Routing from './pages/Routing'
import Protocol from './pages/Protocol'
import Reliability from './pages/Reliability'
import Security from './pages/Security'
import Simulator from './pages/Simulator'

const PRIMARY = [
  { to: '/', label: 'Overview', end: true },
  { to: '/demo', label: 'Live demo' },
  { to: '/node', label: 'Node view' },
  { to: '/rescue', label: 'Rescue dashboard' },
]
const ENGINE = [
  { to: '/routing', label: 'Routing', note: 'Link-state gossip and Dijkstra' },
  { to: '/reliability', label: 'Reliability', note: 'ACK, retry, dedup, store-and-forward' },
  { to: '/protocol', label: 'Wire protocol', note: 'The 52-byte header, byte by byte' },
  { to: '/security', label: 'Security', note: 'AES-256-GCM and Ed25519' },
]
const TAIL = [{ to: '/simulator', label: 'Simulator' }]

const link = ({ isActive }) =>
  cx('rounded-lg px-3 py-2 text-[13.5px] font-medium transition-colors', isActive ? 'bg-crimson-50 text-crimson-700' : 'text-ink-soft hover:bg-wash-2 hover:text-ink')

function ConnectionDot() {
  const { connected, snapshot } = useLab()
  const online = snapshot?.stats?.nodes_online
  return (
    <div className="hidden items-center gap-2 rounded-full border border-line px-3 py-1.5 text-xs text-ink-soft sm:flex" title={connected ? 'Live connection to the mesh server' : 'Reconnecting…'}>
      <span className={cx('h-2 w-2 rounded-full', connected ? 'bg-ok' : 'bg-warn animate-pulse')} />
      {connected ? (online != null ? `${online}/${snapshot.stats.nodes_total} nodes live` : 'Connected') : 'Reconnecting'}
    </div>
  )
}

function EngineMenu() {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  const active = ENGINE.some((e) => pathname.startsWith(e.to))
  useEffect(() => setOpen(false), [pathname])
  return (
    <div className="relative" onMouseLeave={() => setOpen(false)}>
      <button
        onMouseEnter={() => setOpen(true)}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className={cx('flex items-center gap-1 rounded-lg px-3 py-2 text-[13.5px] font-medium transition-colors', active ? 'bg-crimson-50 text-crimson-700' : 'text-ink-soft hover:bg-wash-2 hover:text-ink')}
      >
        Under the hood <ChevronDown size={14} className={cx('transition-transform', open && 'rotate-180')} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.12 }}
            className="absolute left-0 top-full z-50 w-72 pt-2"
          >
            <div className="rounded-2xl border border-line bg-white p-2 shadow-[0_12px_40px_-12px_rgba(63,44,30,0.25)]">
              {ENGINE.map((e) => (
                <NavLink key={e.to} to={e.to} className={({ isActive }) => cx('block rounded-xl px-3 py-2.5 transition-colors', isActive ? 'bg-crimson-50' : 'hover:bg-wash')}>
                  <div className="text-sm font-medium text-ink">{e.label}</div>
                  <div className="text-xs text-muted">{e.note}</div>
                </NavLink>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function Header() {
  const [mobile, setMobile] = useState(false)
  const { pathname } = useLocation()
  useEffect(() => setMobile(false), [pathname])
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-white/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-[1280px] items-center justify-between gap-6 px-5 sm:px-8">
        <NavLink to="/" className="flex items-center gap-2.5"><Logo /></NavLink>
        <nav className="hidden items-center gap-0.5 lg:flex">
          {PRIMARY.map((n) => <NavLink key={n.to} to={n.to} end={n.end} className={link}>{n.label}</NavLink>)}
          <EngineMenu />
          {TAIL.map((n) => <NavLink key={n.to} to={n.to} className={link}>{n.label}</NavLink>)}
        </nav>
        <div className="flex items-center gap-3">
          <ConnectionDot />
          <button className="grid h-10 w-10 place-items-center rounded-lg border border-line lg:hidden" onClick={() => setMobile((m) => !m)} aria-label="Menu">
            {mobile ? <X size={18} /> : <Menu size={18} />}
          </button>
        </div>
      </div>
      <AnimatePresence>
        {mobile && (
          <motion.nav initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden border-t border-line bg-white lg:hidden">
            <div className="flex flex-col gap-1 p-4">
              {[...PRIMARY, ...ENGINE, ...TAIL].map((n) => <NavLink key={n.to} to={n.to} end={n.end} className={link}>{n.label}</NavLink>)}
            </div>
          </motion.nav>
        )}
      </AnimatePresence>
    </header>
  )
}

function Footer() {
  return (
    <footer className="mt-24 border-t border-line">
      <div className="mx-auto flex max-w-[1280px] flex-col gap-4 px-5 py-10 text-sm text-muted sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <div className="flex items-center gap-3"><Logo small /><span>Distributed Peer-to-Peer Disaster Relief Communication Mesh</span></div>
        <div>TE Sem V Mini Project I · Computer Engineering, SPIT · Group 20</div>
      </div>
    </footer>
  )
}

function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => window.scrollTo(0, 0), [pathname])
  return null
}

export default function App() {
  const { pathname } = useLocation()
  const bare = pathname === '/node' || pathname.startsWith('/node/')
  return (
    <div className="flex min-h-screen flex-col bg-white">
      <ScrollToTop />
      <Header />
      <main className={cx('mx-auto w-full flex-1', bare ? 'max-w-[1280px] px-4 pt-8 sm:px-8' : 'max-w-[1280px] px-5 pt-10 sm:px-8')}>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/demo" element={<Demo />} />
          <Route path="/node/:id?" element={<NodeView />} />
          <Route path="/rescue" element={<Rescue />} />
          <Route path="/routing" element={<Routing />} />
          <Route path="/reliability" element={<Reliability />} />
          <Route path="/protocol" element={<Protocol />} />
          <Route path="/security" element={<Security />} />
          <Route path="/simulator" element={<Simulator />} />
          <Route path="*" element={<Overview />} />
        </Routes>
      </main>
      <Footer />
    </div>
  )
}
