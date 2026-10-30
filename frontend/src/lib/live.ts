import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { api } from './api'
import { useAuth } from './auth'

export type LiveState = 'connecting' | 'live' | 'offline'

interface LiveMessage {
  type: 'instrument' | 'alert'
  data: Record<string, unknown>
}

/** Subscribes to server events and refreshes affected views, so dashboards stay current without reloading. */
export function useLiveUpdates(): LiveState {
  const { user, isGlobal } = useAuth()
  const qc = useQueryClient()
  const [state, setState] = useState<LiveState>('connecting')
  const source = useRef<EventSource | null>(null)
  const retry = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pending = useRef<Set<string>>(new Set())
  const flush = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!user) return
    let stopped = false

    const invalidate = (...keys: string[]) => {
      keys.forEach((k) => pending.current.add(k))
      if (flush.current) return
      // Batch bursts (e.g. a bulk import) into one refetch.
      flush.current = setTimeout(() => {
        pending.current.forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
        pending.current.clear()
        flush.current = null
      }, 400)
    }

    const handle = (msg: LiveMessage) => {
      if (msg.type === 'instrument') {
        invalidate('instruments', 'instrument', 'dashboard', 'institution', 'institutions', 'my-work')
      } else if (msg.type === 'alert') {
        invalidate('alerts', 'unread')
        const d = msg.data as { severity?: string; title?: string; message?: string; kind?: string }
        const loud = d.severity === 'CRITICAL' || d.severity === 'HIGH'
        if (!isGlobal || loud) {
          const fn = loud ? toast.warning : toast.info
          fn(d.title ?? 'New alert', { description: d.message?.slice(0, 160) })
        }
      }
    }

    const connect = async () => {
      if (stopped) return
      setState('connecting')
      try {
        const { token } = await api.post<{ token: string }>('/stream/token')
        if (stopped) return
        const es = new EventSource(`/api/stream?token=${encodeURIComponent(token)}`)
        source.current = es
        es.addEventListener('ready', () => setState('live'))
        es.onmessage = (ev) => {
          try {
            handle(JSON.parse(ev.data))
          } catch {
            /* ignore malformed */
          }
        }
        es.onerror = () => {
          es.close()
          setState('offline')
          retry.current = setTimeout(connect, 5000)
        }
      } catch {
        setState('offline')
        retry.current = setTimeout(connect, 10000)
      }
    }
    connect()
    return () => {
      stopped = true
      source.current?.close()
      if (retry.current) clearTimeout(retry.current)
      if (flush.current) clearTimeout(flush.current)
    }
  }, [user, qc, isGlobal])

  return state
}
