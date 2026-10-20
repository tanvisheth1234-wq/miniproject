import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'

/**
 * One WebSocket for the whole app. The server pushes:
 *   hello     the first message: a snapshot plus recent history
 *   snapshot  the whole mesh a few times a second while anything changes
 *   event     one engine event (sent, forward, recv, ack, retry, ...)
 *   lab       an operator action (node switched off, link cut, ...)
 * Events are also fanned out immediately to `subscribe()` listeners so the
 * graph can animate a packet the instant it moves, without waiting for React.
 */
const LabContext = createContext(null)

const MAX_EVENTS = 400
const MAX_ACTIONS = 120

export function LabProvider({ children }) {
  const [snapshot, setSnapshot] = useState(null)
  const [events, setEvents] = useState([])
  const [actions, setActions] = useState([])
  const [connected, setConnected] = useState(false)
  const [version, setVersion] = useState(0) // bumps on every snapshot; pages refetch on it

  const listeners = useRef(new Set())
  const pending = useRef({ events: [], actions: [] })

  const subscribe = useCallback((fn) => {
    listeners.current.add(fn)
    return () => listeners.current.delete(fn)
  }, [])

  useEffect(() => {
    let socket
    let retry
    let closed = false
    let attempt = 0

    const open = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      socket = new WebSocket(`${proto}://${location.host}/ws`)
      socket.onopen = () => {
        attempt = 0
        setConnected(true)
      }
      socket.onmessage = (msg) => {
        const data = JSON.parse(msg.data)
        if (data.type === 'hello') {
          setSnapshot(data.snapshot)
          setEvents(data.events.slice(-MAX_EVENTS))
          setActions(data.actions.slice(-MAX_ACTIONS))
          setVersion((v) => v + 1)
        } else if (data.type === 'snapshot') {
          setSnapshot(data.snapshot)
          setVersion((v) => v + 1)
        } else if (data.type === 'event') {
          pending.current.events.push(data)
          listeners.current.forEach((fn) => fn(data))
        } else if (data.type === 'lab') {
          pending.current.actions.push(data)
        }
      }
      socket.onclose = () => {
        setConnected(false)
        if (!closed) retry = setTimeout(open, Math.min(4000, 400 * 2 ** attempt++))
      }
      socket.onerror = () => socket.close()
    }
    open()

    // batch bursts of events into one render
    const flush = setInterval(() => {
      const { events: e, actions: a } = pending.current
      if (e.length) {
        pending.current.events = []
        setEvents((prev) => [...prev, ...e].slice(-MAX_EVENTS))
      }
      if (a.length) {
        pending.current.actions = []
        setActions((prev) => [...prev, ...a].slice(-MAX_ACTIONS))
      }
    }, 150)

    return () => {
      closed = true
      clearTimeout(retry)
      clearInterval(flush)
      socket?.close()
    }
  }, [])

  const value = useMemo(
    () => ({ snapshot, events, actions, connected, version, subscribe }),
    [snapshot, events, actions, connected, version, subscribe],
  )
  return <LabContext.Provider value={value}>{children}</LabContext.Provider>
}

export function useLab() {
  const ctx = useContext(LabContext)
  if (!ctx) throw new Error('useLab must be used inside <LabProvider>')
  return ctx
}

/**
 * Fetch `path` now and again whenever the mesh changes (at most once a
 * second). Returns { data, error, reload }. Pass `null` to pause.
 */
export function useLive(path, { every = 1000 } = {}) {
  const { version } = useLab()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const last = useRef(0)
  const timer = useRef()
  const alive = useRef(true)

  const load = useCallback(async () => {
    if (!path) return
    last.current = Date.now()
    try {
      const next = await api.get(path)
      if (alive.current) {
        setData(next)
        setError(null)
      }
    } catch (e) {
      if (alive.current) setError(e)
    }
  }, [path])

  useEffect(() => {
    alive.current = true
    setData(null)
    last.current = 0
    return () => { alive.current = false }
  }, [path])

  useEffect(() => {
    if (!path) return undefined
    const wait = Math.max(0, every - (Date.now() - last.current))
    clearTimeout(timer.current)
    timer.current = setTimeout(load, wait)
    return () => clearTimeout(timer.current)
  }, [path, version, every, load])

  return { data, error, reload: load }
}

/** Run an async action, tracking busy and error state for a button. */
export function useAction(fn) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const run = useCallback(
    async (...args) => {
      setBusy(true)
      setError(null)
      try {
        return await fn(...args)
      } catch (e) {
        setError(e.message)
        return undefined
      } finally {
        setBusy(false)
      }
    },
    [fn],
  )
  return { run, busy, error, clear: () => setError(null) }
}
