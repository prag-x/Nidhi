import { keepPreviousData, useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { useState } from 'react'
import { MaturityChart } from '@/components/charts/Charts'
import InstrumentTable from '@/components/InstrumentTable'
import { Card, ErrorState, Loading, PageHeader, Pagination } from '@/components/ui'
import { api } from '@/lib/api'
import { fmtLakh, fmtNumber } from '@/lib/format'
import { t } from '@/lib/i18n'
import type { InstrumentItem, Page } from '@/lib/types'
import type { Summary } from './Home'

function monthEnd(iso: string) {
  const d = new Date(iso + 'T00:00:00')
  d.setMonth(d.getMonth() + 1)
  d.setDate(0)
  return d.toISOString().slice(0, 10)
}

export default function Maturity() {
  const sum = useQuery({ queryKey: ['dashboard', 'summary'], queryFn: () => api.get<Summary>('/dashboard/summary') })
  const [month, setMonth] = useState<string>('overdue')
  const [page, setPage] = useState(1)
  const params = month === 'overdue'
    ? { matured_unrenewed: true, sort: 'maturity', order: 'asc' }
    : { status: 'HELD', maturity_from: month, maturity_to: monthEnd(month), sort: 'maturity', order: 'asc' }
  const list = useQuery({
    queryKey: ['instruments', 'maturity', month, page],
    queryFn: () => api.get<Page<InstrumentItem>>('/instruments', { ...params, page, page_size: 25 }),
    placeholderData: keepPreviousData,
  })
  if (sum.isLoading) return <Loading />
  if (sum.error) return <ErrorState error={sum.error} retry={sum.refetch} />
  const s = sum.data!
  return (
    <div>
      <PageHeader title={t('Maturity calendar')} subtitle={t('Reminders go out at 90, 60, 30 and 7 days before maturity, to the institution and the dealing officer, until a renewal is lodged.')} />
      <Card className="mb-5 p-4">
        <MaturityChart data={s.calendar} onSelect={(m) => { setMonth(m); setPage(1) }} />
      </Card>
      <p className="mb-2 text-[13px] text-slate-500">{t('Darker months have more FDRs maturing; the violet line under each shows how many already have a renewal lodged.')}</p>
      <div className="mb-5 grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-7">
        <button onClick={() => { setMonth('overdue'); setPage(1) }}
          className={clsx('rounded-[8px] border px-3 py-2 text-left transition-shadow hover:shadow-md', month === 'overdue' ? 'border-seal-600 bg-seal-600 text-white [&_span]:!text-white' : 'border-seal-100 bg-seal-50')}>
          <span className="block text-[12.5px] text-seal-700">{t('Matured')}</span>
          <span className="figure block text-[22px] leading-tight text-seal-600">{fmtNumber(s.kpis.matured_unrenewed)}</span>
          <span className="block text-[12px] text-slate-500">{fmtLakh(s.kpis.matured_amount)}</span>
        </button>
        {s.calendar.map((m) => {
          const pending = m.count - m.renewal_lodged
          const max = Math.max(1, ...s.calendar.map((c) => c.count))
          const heat = m.count / max
          return (
            <button key={m.month} onClick={() => { setMonth(m.month); setPage(1) }}
              style={{ background: month === m.month ? undefined : `rgba(31,138,128,${0.06 + heat * 0.32})` }}
              className={clsx('relative overflow-hidden rounded-[8px] border px-3 py-2 text-left transition-shadow hover:shadow-md', month === m.month ? 'border-brand-800 bg-brand-800 text-white [&_span]:!text-white' : 'border-transparent')}>
              {m.renewal_lodged > 0 && <span className="absolute inset-x-0 bottom-0 h-1 bg-ink-green-500" style={{ width: `${(100 * m.renewal_lodged) / Math.max(1, m.count)}%` }} />}
              <span className="block text-[12.5px] text-slate-500">{new Date(m.month + 'T00:00:00').toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })}</span>
              <span className="figure block text-[22px] leading-tight text-brand-900">{fmtNumber(m.count)}</span>
              <span className="block text-[12px] text-slate-500">
                {pending > 0 ? t('{n} to renew', { n: pending }) : t('all renewed')}
                {m.high_risk > 0 && <span className="text-seal-600"> · {m.high_risk} {t('late?')}</span>}
              </span>
            </button>
          )
        })}
      </div>
      <Card>
        {list.isLoading ? <Loading /> : list.error ? <ErrorState error={list.error} /> : (
          <>
            <InstrumentTable items={list.data!.items} showRisk empty={t('Nothing matures this month.')} />
            <Pagination page={page} pageSize={25} total={list.data!.total} onChange={setPage} />
          </>
        )}
      </Card>
    </div>
  )
}
