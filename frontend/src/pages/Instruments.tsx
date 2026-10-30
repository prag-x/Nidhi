import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Download, Plus, RotateCcw } from 'lucide-react'
import { useEffect, useState } from 'react'
import InstrumentTable from '@/components/InstrumentTable'
import { Button, ButtonLink, ErrorState, Input, Loading, PageHeader, Pagination, Select, Tabs } from '@/components/ui'
import { api, download, errorMessage } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtNumber } from '@/lib/format'
import { useDebounced, useMeta, useUrlFilters } from '@/lib/hooks'
import { t } from '@/lib/i18n'
import type { InstrumentItem, Page } from '@/lib/types'
import { toast } from 'sonner'

const DEFAULTS = {
  q: '', status: '', purpose: '', bank_id: '', region_id: '', verification: '', discrepancy: '', expiring_days: '',
  matured_unrenewed: '', at_risk: '', assigned: '', institution_id: '', min_amount: '', max_amount: '',
  maturity_from: '', maturity_to: '', sort: 'submitted', order: 'desc', page: '1',
}

const VIEWS = [
  { value: 'all', label: t('All'), patch: {} },
  { value: 'held', label: t('Held'), patch: { status: 'HELD' } },
  { value: 'pending', label: t('Pending scrutiny'), patch: { status: 'PENDING' } },
  { value: 'expiring', label: t('Maturing in 90 days'), patch: { expiring_days: '90', sort: 'maturity', order: 'asc' } },
  { value: 'matured', label: t('Matured, not renewed'), patch: { matured_unrenewed: 'true', sort: 'maturity', order: 'asc' } },
  { value: 'disc', label: t('With discrepancies'), patch: { discrepancy: 'any' } },
  { value: 'closed', label: t('Renewed, released, rejected'), patch: { status: 'CLOSED' } },
] as const

export default function Instruments() {
  const { isStaff, canLodge, isInstitution, user } = useAuth()
  const meta = useMeta()
  const { values: f, set, reset } = useUrlFilters(DEFAULTS)
  const [q, setQ] = useState(f.q)
  const dq = useDebounced(q, 300)
  useEffect(() => {
    if (dq !== f.q) set({ q: dq })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dq])
  const params = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== ''))
  const list = useQuery({
    queryKey: ['instruments', params],
    queryFn: () => api.get<Page<InstrumentItem>>('/instruments', { ...params, page_size: 25 }),
    placeholderData: keepPreviousData,
  })
  const view = VIEWS.find((v) => {
    const keys = Object.keys(v.patch) as (keyof typeof f)[]
    return keys.length > 0 && keys.every((k) => f[k] === (v.patch as Record<string, string>)[k])
  })?.value ?? (Object.entries(f).some(([k, v]) => !['sort', 'order', 'page', 'q'].includes(k) && v) ? '' : 'all')
  const exportAs = async (format: 'xlsx' | 'csv') => {
    try {
      await download('/instruments/export', { ...params, format }, `deposits.${format}`)
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }
  return (
    <div>
      <PageHeader
        title={isInstitution ? t('Our deposits') : t('Deposits & FDRs')}
        subtitle={isInstitution ? user?.institution?.name : t('Every security deposit and FDR lodged with AICTE, institution-wise and instrument-wise.')}
        actions={
          <>
            {isStaff && (
              <>
                <Button size="sm" icon={<Download className="size-4" />} onClick={() => exportAs('xlsx')}>{t('Excel')}</Button>
                <Button size="sm" onClick={() => exportAs('csv')}>CSV</Button>
              </>
            )}
            {canLodge && <ButtonLink to="/instruments/new" variant="primary" size="sm" icon={<Plus className="size-4" />}>{t('Lodge')}</ButtonLink>}
          </>
        }
      />
      <Tabs
        tabs={VIEWS.map((v) => ({ value: v.value, label: v.label }))}
        value={view as (typeof VIEWS)[number]['value']}
        onChange={(v) => {
          const patch = VIEWS.find((x) => x.value === v)!.patch
          reset()
          setTimeout(() => set(patch as Partial<typeof DEFAULTS>), 0)
        }}
      />
      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('FDR number, reference, institution, society…')} className="lg:col-span-2" aria-label={t('Search')} />
        <Select value={f.bank_id} onChange={(e) => set({ bank_id: e.target.value })} aria-label={t('Bank')}>
          <option value="">{t('Any bank')}</option>
          {meta.data?.banks.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
        </Select>
        {isStaff && (
          <Select value={f.region_id} onChange={(e) => set({ region_id: e.target.value })} aria-label={t('Region')}>
            <option value="">{t('Any region')}</option>
            {meta.data?.regions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </Select>
        )}
        <Select value={f.verification} onChange={(e) => set({ verification: e.target.value })} aria-label={t('Bank verification')}>
          <option value="">{t('Any verification')}</option>
          {meta.data?.verification.map((v) => <option key={v.value} value={v.value}>{t(v.label)}</option>)}
        </Select>
        <Select value={`${f.sort}:${f.order}`} onChange={(e) => { const [sort, order] = e.target.value.split(':'); set({ sort, order }) }} aria-label={t('Sort')}>
          <option value="submitted:desc">{t('Newest lodged')}</option>
          <option value="maturity:asc">{t('Maturing first')}</option>
          <option value="amount:desc">{t('Largest amount')}</option>
          <option value="risk:desc">{t('Most likely late')}</option>
          <option value="updated:desc">{t('Recently updated')}</option>
        </Select>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-[13.5px] text-slate-600">
        {isStaff && (
          <label className="inline-flex items-center gap-1.5">
            <input type="checkbox" checked={f.assigned === 'me'} onChange={(e) => set({ assigned: e.target.checked ? 'me' : '' })} />
            {t('Assigned to me')}
          </label>
        )}
        {isStaff && (
          <label className="inline-flex items-center gap-1.5">
            <input type="checkbox" checked={f.at_risk === 'true'} onChange={(e) => set({ at_risk: e.target.checked ? 'true' : '' })} />
            {t('Likely to renew late')}
          </label>
        )}
        {(f.maturity_from || f.maturity_to) && <span>{t('Maturing')} {f.maturity_from} – {f.maturity_to}</span>}
        {f.institution_id && <span>{t('One institution')}</span>}
        <button onClick={() => { setQ(''); reset() }} className="inline-flex items-center gap-1 text-brand-700 hover:underline">
          <RotateCcw className="size-3.5" /> {t('Clear filters')}
        </button>
        <span className="ml-auto figure text-slate-500">{list.data ? t('{n} deposits', { n: fmtNumber(list.data.total) }) : ''}</span>
      </div>
      <div className="sheet mt-3">
        {list.isLoading ? <Loading /> : list.error ? <ErrorState error={list.error} retry={list.refetch} /> : (
          <>
            <InstrumentTable items={list.data!.items} showInstitution={!isInstitution} showRisk={isStaff && (f.at_risk === 'true' || f.sort === 'risk')} empty={t('No deposits match these filters.')} />
            <Pagination page={Number(f.page)} pageSize={25} total={list.data!.total} onChange={(p) => set({ page: String(p) }, true)} />
          </>
        )}
      </div>
    </div>
  )
}
