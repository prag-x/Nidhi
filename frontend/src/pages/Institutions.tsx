import { keepPreviousData, useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Building2, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { RiskStrip } from '@/components/Risk'
import { Card, EmptyState, ErrorState, Input, Loading, PageHeader, Pagination, Select, Toggle } from '@/components/ui'
import { api } from '@/lib/api'
import { fmtLakh, fmtNumber } from '@/lib/format'
import { useDebounced, useMeta, useUrlFilters } from '@/lib/hooks'
import type { Institution, Page } from '@/lib/types'
import { t } from '@/lib/i18n'

const DEFAULTS = { q: '', region_id: '', state_code: '', sort: 'attention', with_deposits: 'true', page: '1' }

export default function Institutions() {
  const meta = useMeta()
  const navigate = useNavigate()
  const { values: f, set } = useUrlFilters(DEFAULTS)
  const [search, setSearch] = useState(f.q)
  const term = useDebounced(search, 300)
  useEffect(() => {
    if (term !== f.q) set({ q: term })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [term])
  const params = { ...f, page_size: 25 }
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ['institutions', params],
    queryFn: () => api.get<Page<Institution>>('/institutions', params),
    placeholderData: keepPreviousData,
  })
  return (
    <div>
      <PageHeader
        title={t('Institutions')}
        subtitle={t('Every institution with a deposit or FDR on record. Those needing action first: matured and unrenewed, then open discrepancies, then maturing soon.')}
      />
      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-4">
          <div className="relative min-w-60 flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('Institution name, city or AICTE Permanent ID')} className="pl-9" />
          </div>
          <Select value={f.region_id} onChange={(e) => set({ region_id: e.target.value })} className="w-auto" aria-label={t('Region')}>
            <option value="">{t('All regions')}</option>
            {meta.data?.regions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </Select>
          <Select value={f.sort} onChange={(e) => set({ sort: e.target.value })} className="w-auto" aria-label={t('Sort')}>
            <option value="attention">{t('Needs attention')}</option>
            <option value="amount">{t('Amount held')}</option>
            <option value="late">{t('Late renewals')}</option>
            <option value="risk">{t('Late-renewal risk')}</option>
            <option value="name">{t('Name')}</option>
          </Select>
          <Toggle checked={f.with_deposits === 'true'} onChange={(v) => set({ with_deposits: v ? 'true' : 'false' })} label={t('Only with deposits')} />
        </div>
        {error ? (
          <ErrorState error={error} retry={refetch} />
        ) : isLoading ? (
          <Loading />
        ) : data?.items.length ? (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/60 text-left text-xs font-medium text-slate-500">
                    <th className="px-4 py-2.5">{t('Institution')}</th>
                    <th className="px-3 py-2.5">{t('Location')}</th>
                    <th className="px-3 py-2.5 text-right">{t('Held')}</th>
                    <th className="px-3 py-2.5 text-right">{t('Amount')}</th>
                    <th className="px-3 py-2.5 text-right">{t('Matured, unrenewed')}</th>
                    <th className="px-3 py-2.5 text-right">{t('Maturing 90 days')}</th>
                    <th className="px-3 py-2.5 text-right">{t('Discrepancies')}</th>
                    <th className="px-3 py-2.5 text-right">{t('Late renewals')}</th>
                    <th className="w-40 px-4 py-2.5">{t('Next renewal risk')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.items.map((i) => {
                    const s = i.stats!
                    return (
                      <tr key={i.id} onClick={() => navigate(`/institutions/${i.id}`)} className="cursor-pointer hover:bg-brand-50/40">
                        <td className="px-4 py-3">
                          <div className="font-medium text-slate-900">{i.name}</div>
                          <div className="text-xs text-slate-500"><span className="tabular">{i.aicte_pid}</span> · {i.inst_type}</div>
                        </td>
                        <td className="px-3 py-3 text-slate-600">
                          {i.city}, {i.state_code}
                          <div className="text-xs text-slate-400">{i.region?.code}</div>
                        </td>
                        <td className="px-3 py-3 text-right tabular">{fmtNumber(s.held)}</td>
                        <td className="figure px-3 py-3 text-right">{fmtLakh(s.held_amount)}</td>
                        <td className={clsx('px-3 py-3 text-right tabular', s.matured_unrenewed ? 'font-semibold text-seal-600' : 'text-slate-400')}>{s.matured_unrenewed || '—'}</td>
                        <td className={clsx('px-3 py-3 text-right tabular', s.expiring ? 'text-turmeric-700' : 'text-slate-400')}>{s.expiring || '—'}</td>
                        <td className={clsx('px-3 py-3 text-right tabular', s.open_discrepancies ? 'text-seal-600' : 'text-slate-400')}>{s.open_discrepancies || '—'}</td>
                        <td className="px-3 py-3 text-right tabular text-slate-600">{s.renewals ? `${s.renewed_late} / ${s.renewals}` : '—'}</td>
                        <td className="px-4 py-3">{s.max_risk !== null ? <RiskStrip value={s.max_risk} /> : <span className="text-slate-400">—</span>}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <Pagination page={Number(f.page)} pageSize={25} total={data.total} onChange={(p) => set({ page: String(p) }, true)} />
          </>
        ) : (
          <EmptyState icon={<Building2 className="size-10" />} title={t('No institutions found')} />
        )}
      </Card>
    </div>
  )
}
