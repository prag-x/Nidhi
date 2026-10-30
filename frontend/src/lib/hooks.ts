import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from './api'
import type { Meta } from './types'

export function useMeta() {
  return useQuery({ queryKey: ['meta'], queryFn: () => api.get<Meta>('/meta'), staleTime: 10 * 60_000 })
}

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => api.get<{ status: string; demo_mode: boolean; version: string; database: string }>('/health'),
    staleTime: 5 * 60_000,
  })
}

export function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

/** Filters kept in the URL so views can be bookmarked and shared. */
export function useUrlFilters<T extends Record<string, string>>(defaults: T) {
  const [params, setParams] = useSearchParams()
  const values = useMemo(() => {
    const out: Record<string, string> = { ...defaults }
    params.forEach((v, k) => {
      out[k] = v
    })
    return out as T
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params])
  const set = useCallback(
    (patch: Partial<T>, keepPage = false) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          for (const [k, v] of Object.entries(patch)) {
            if (v === undefined || v === null || v === '' || v === defaults[k]) next.delete(k)
            else next.set(k, String(v))
          }
          if (!keepPage && !('page' in patch)) next.delete('page')
          return next
        },
        { replace: true },
      )
    },
    [setParams, defaults],
  )
  const reset = useCallback(() => setParams(new URLSearchParams(), { replace: true }), [setParams])
  return { values, set, reset }
}

export function useBankName() {
  const { data } = useMeta()
  return useCallback((id: number | null | undefined) => data?.banks.find((b) => b.id === id)?.short_name ?? '', [data])
}
