import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { BellOff, Check, CheckCheck } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, EmptyState, ErrorState, Loading, PageHeader, Pagination, RefNo, Select, Toggle } from '@/components/ui'
import { api } from '@/lib/api'
import { fmtDateTime, timeAgo } from '@/lib/format'
import { useUrlFilters } from '@/lib/hooks'
import { ALERT_KIND, SEVERITY } from '@/lib/labels'
import type { AlertItem } from '@/lib/types'
import { t } from '@/lib/i18n'

const DEFAULTS = { status: 'open', kind: '', unread: '', page: '1' }

export default function Alerts() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { values: f, set } = useUrlFilters(DEFAULTS)
  const params = { ...f, unread: f.unread === 'true', page_size: 30 }
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ['alerts', params],
    queryFn: () => api.get<{ total: number; open_by_kind: Record<string, number>; items: AlertItem[] }>('/alerts', params),
    placeholderData: keepPreviousData,
  })
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['alerts'] })
    qc.invalidateQueries({ queryKey: ['unread'] })
  }
  const readAll = useMutation({ mutationFn: () => api.post('/alerts/read-all'), onSuccess: refresh })
  const ack = useMutation({ mutationFn: (id: number) => api.post(`/alerts/${id}/acknowledge`), onSuccess: refresh })
  const open = async (a: AlertItem) => {
    if (!a.read) api.post(`/alerts/${a.id}/read`).then(refresh).catch(() => undefined)
    if (a.instrument_id) navigate(`/instruments/${a.instrument_id}`)
  }
  const kinds = Object.entries(data?.open_by_kind ?? {}).sort((a, b) => b[1] - a[1])

  return (
    <div>
      <PageHeader
        title={t('Alerts and reminders')}
        subtitle={t('Maturity reminders, unrenewed FDRs, bank replies awaited, discrepancies, fraud signals, releases and escalations')}
        actions={<Button size="sm" icon={<CheckCheck className="size-4" />} loading={readAll.isPending} onClick={() => readAll.mutate()}>{t('Mark all read')}</Button>}
      />
      <div className="mb-4 flex flex-wrap gap-2">
        <button onClick={() => set({ kind: '' })} className={clsx('rounded-full px-3 py-1 text-xs font-medium', !f.kind ? 'bg-brand-800 text-white' : 'bg-white text-slate-600 ring-1 ring-slate-200')}>
          {t('All open')}
        </button>
        {kinds.map(([k, n]) => (
          <button key={k} onClick={() => set({ kind: k })} className={clsx('rounded-full px-3 py-1 text-xs font-medium', f.kind === k ? 'bg-brand-800 text-white' : 'bg-white text-slate-600 ring-1 ring-slate-200')}>
            {ALERT_KIND[k] ?? k} <span className="tabular opacity-70">{n}</span>
          </button>
        ))}
      </div>
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 p-4">
          <Select value={f.status} onChange={(e) => set({ status: e.target.value })} className="w-auto" aria-label={t('Status')}>
            <option value="open">{t('Open')}</option>
            <option value="ACKNOWLEDGED">{t('Acknowledged')}</option>
            <option value="RESOLVED">{t('Resolved')}</option>
            <option value="all">{t('All')}</option>
          </Select>
          <Toggle checked={f.unread === 'true'} onChange={(v) => set({ unread: v ? 'true' : '' })} label={t('Unread only')} />
        </div>
        {error ? (
          <ErrorState error={error} retry={refetch} />
        ) : isLoading ? (
          <Loading />
        ) : data?.items.length ? (
          <>
            <ul className="divide-y divide-slate-100">
              {data.items.map((a) => (
                <li key={a.id} className={clsx('flex gap-3 px-4 py-3', !a.read && 'bg-brand-50/40')}>
                  <span className={clsx('mt-1.5 size-2.5 shrink-0 rounded-full', SEVERITY[a.severity].dot)} title={SEVERITY[a.severity].label} />
                  <button className="min-w-0 flex-1 text-left" onClick={() => open(a)}>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                      <span className="font-medium text-slate-700">{ALERT_KIND[a.kind] ?? a.kind}</span>
                      {a.ref_no && <RefNo>{a.ref_no}</RefNo>}
                      <span title={fmtDateTime(a.created_at)}>{timeAgo(a.created_at)}</span>
                      {a.status !== 'OPEN' && <span className="text-ink-green-700">{a.status.toLowerCase()}</span>}
                    </div>
                    <div className={clsx('mt-0.5 text-sm', a.read ? 'text-slate-700' : 'font-semibold text-slate-900')}>{a.title}</div>
                    <div className="mt-0.5 line-clamp-2 text-sm text-slate-500">{a.message}</div>
                  </button>
                  {a.status === 'OPEN' && (
                    <Button size="xs" variant="ghost" icon={<Check className="size-3.5" />} onClick={() => ack.mutate(a.id)} title={t('Acknowledge')}>
                      <span className="hidden sm:inline">{t('Acknowledge')}</span>
                    </Button>
                  )}
                </li>
              ))}
            </ul>
            <Pagination page={Number(f.page)} pageSize={30} total={data.total} onChange={(p) => set({ page: String(p) }, true)} />
          </>
        ) : (
          <EmptyState icon={<BellOff className="size-10" />} title={t('No alerts here')} />
        )}
      </Card>
    </div>
  )
}
