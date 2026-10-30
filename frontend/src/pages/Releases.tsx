import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useState } from 'react'
import { Card, EmptyState, ErrorState, Loading, PageHeader, Pagination, RefNo, Tabs } from '@/components/ui'
import { api } from '@/lib/api'
import { fmtDate, fmtLakh } from '@/lib/format'
import { t } from '@/lib/i18n'
import { RELEASE_STEPS } from '@/lib/labels'
import type { InstrumentItem, Page, ReleaseOut } from '@/lib/types'

type Row = ReleaseOut & { instrument: InstrumentItem }
const TABS = [
  { value: 'open', label: t('In progress') },
  { value: 'REQUESTED', label: t('To recommend') },
  { value: 'RECOMMENDED', label: t('To approve') },
  { value: 'APPROVED', label: t('To execute') },
  { value: 'EXECUTED', label: t('Released') },
  { value: 'REJECTED', label: t('Not approved') },
] as const

export default function Releases() {
  const [tab, setTab] = useState<(typeof TABS)[number]['value']>('open')
  const [page, setPage] = useState(1)
  const q = useQuery({
    queryKey: ['releases', tab, page],
    queryFn: () => api.get<Page<Row>>('/releases', { status: tab, page, page_size: 30 }),
    placeholderData: keepPreviousData,
  })
  return (
    <div>
      <PageHeader title={t('Release and refund requests')} subtitle={t('Each request moves from the Regulation Bureau to the competent authority to Accounts. The same person can never both recommend and approve.')} />
      <Tabs tabs={TABS.map((x) => ({ value: x.value, label: x.label }))} value={tab} onChange={(v) => { setTab(v); setPage(1) }} />
      <Card className="mt-4">
        {q.isLoading ? <Loading /> : q.error ? <ErrorState error={q.error} retry={q.refetch} /> : !q.data!.items.length ? <EmptyState title={t('No requests here.')} /> : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-[14.5px]">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-[12.5px] text-slate-500">
                    <th className="px-4 py-2 font-normal">{t('Reference')}</th>
                    <th className="px-3 py-2 font-normal">{t('Institution')}</th>
                    <th className="px-3 py-2 font-normal">{t('Reason')}</th>
                    <th className="px-3 py-2 text-right font-normal">{t('Amount')}</th>
                    <th className="px-3 py-2 font-normal">{t('Stage')}</th>
                  </tr>
                </thead>
                <tbody>
                  {q.data!.items.map((r) => {
                    const idx = RELEASE_STEPS.findIndex((s) => s.key === r.status)
                    return (
                      <tr key={r.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                        <td className="px-4 py-2.5"><Link to={`/instruments/${r.instrument.id}`}><RefNo>{r.instrument.ref_no}</RefNo></Link>
                          <div className="text-[12.5px] text-slate-500">{t('requested')} {fmtDate(r.requested_at)}</div></td>
                        <td className="px-3 py-2.5 text-brand-900">{r.instrument.institution.name}<div className="text-[12.5px] text-slate-500">{r.instrument.institution.city}</div></td>
                        <td className="px-3 py-2.5">{t(r.reason_label)}</td>
                        <td className="figure px-3 py-2.5 text-right">{fmtLakh(r.instrument.amount)}</td>
                        <td className="px-3 py-2.5">
                          {r.status === 'REJECTED' ? <span className="text-seal-700">{t('Not approved')}</span> : (
                            <span className="flex items-center gap-1" title={RELEASE_STEPS[idx]?.label}>
                              {RELEASE_STEPS.map((s, i) => <span key={s.key} className={i <= idx ? 'h-1.5 w-6 rounded-full bg-ink-green-600' : 'h-1.5 w-6 rounded-full bg-slate-200'} />)}
                              <span className="ml-2 text-[13px] text-slate-600">{RELEASE_STEPS[idx]?.label}</span>
                            </span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <Pagination page={page} pageSize={30} total={q.data!.total} onChange={setPage} />
          </>
        )}
      </Card>
    </div>
  )
}
