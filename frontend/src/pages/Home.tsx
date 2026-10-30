import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import AskPanel from '@/components/AskPanel'
import InstrumentLine from '@/components/InstrumentLine'
import { RiskStrip } from '@/components/Risk'
import { ButtonLink, ErrorState, Loading, PageHeader, RefNo, Stat } from '@/components/ui'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDate, fmtLakh, fmtNumber, fmtPct, greeting } from '@/lib/format'
import { t } from '@/lib/i18n'
import type { InstrumentItem, ReleaseOut } from '@/lib/types'

interface Queue {
  key: string
  title: string
  hint: string
  count: number
  items: (InstrumentItem | (ReleaseOut & { instrument: InstrumentItem }))[]
}
export interface Summary {
  as_of: string
  kpis: Record<string, number | null>
  calendar: { month: string; count: number; amount: number; renewal_lodged: number; high_risk: number }[]
  trend: { month: string; lodged: number; accepted: number; released: number; renewed_late: number }[]
  by_status: { status: string; label: string; count: number; amount: number }[]
  by_bank: { bank_id: number; name: string; short_name: string; count: number; amount: number; problems: number }[]
  by_region: { region_id: number; name: string; city: string; held: number; amount: number; expiring: number; matured: number; pending: number }[]
  watch: { matured: InstrumentItem[]; expiring: InstrumentItem[]; at_risk: InstrumentItem[] }
}

function isRelease(x: Queue['items'][number]): x is ReleaseOut & { instrument: InstrumentItem } {
  return 'instrument' in x
}

function QueueBlock({ q }: { q: Queue }) {
  return (
    <section className="sheet">
      <div className="flex items-baseline justify-between gap-3 border-b border-slate-200 px-4 py-3">
        <div>
          <h2 className="text-[19px] font-semibold text-brand-900">
            {t(q.title)} <span className="figure ml-1 text-slate-400">{fmtNumber(q.count)}</span>
          </h2>
          {q.hint && <p className="text-[13px] text-slate-500">{t(q.hint)}</p>}
        </div>
      </div>
      {q.items.length === 0 ? (
        <p className="px-4 py-6 text-[14px] text-slate-500">{t('Nothing waiting.')}</p>
      ) : (
        <div>
          {q.items.slice(0, 8).map((x) =>
            isRelease(x) ? (
              <Link key={`r${x.id}`} to={`/instruments/${x.instrument.id}`} className="flex flex-wrap items-center gap-3 border-b border-slate-100 px-4 py-2.5 last:border-0 hover:bg-slate-50">
                <RefNo>{x.instrument.ref_no}</RefNo>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[15px] text-brand-900">{x.instrument.institution.name}, {x.instrument.institution.city}</span>
                  <span className="text-[13px] text-slate-500">{x.reason_label} · {t('requested')} {fmtDate(x.requested_at)}</span>
                </span>
                <span className="figure text-[16px] text-brand-900">{fmtLakh(x.instrument.amount)}</span>
              </Link>
            ) : (
              <InstrumentLine key={x.id} x={x} right={q.key === 'risk' ? <RiskStrip value={x.renewal_risk} /> : undefined} />
            ),
          )}
          {q.count > 8 && <p className="px-4 py-2 text-[13px] text-slate-500">{t('and {n} more', { n: q.count - 8 })}</p>}
        </div>
      )}
    </section>
  )
}

export default function Home() {
  const { user, isStaff, isInstitution, canLodge } = useAuth()
  const my = useQuery({ queryKey: ['my-work'], queryFn: () => api.get<{ queues: Queue[] }>('/dashboard/my') })
  const sum = useQuery({ queryKey: ['dashboard', 'summary'], queryFn: () => api.get<Summary>('/dashboard/summary') })
  if (my.isLoading) return <Loading />
  if (my.error) return <ErrorState error={my.error} retry={my.refetch} />
  const k = sum.data?.kpis ?? {}
  const title = isInstitution ? user?.institution?.name ?? '' : `${greeting()}, ${user?.full_name.split(' ').slice(-1)[0]}`
  return (
    <div>
      <PageHeader
        title={title}
        subtitle={isInstitution
          ? t('Deposits and FDRs you have lodged with AICTE, and what needs doing.')
          : t('What needs your attention today, from deposits held by AICTE.')}
        actions={canLodge && (
          <ButtonLink to="/instruments/new" variant="primary" icon={<Plus className="size-4" />}>
            {isInstitution ? t('Lodge an FDR or renewal') : t('Lodge on behalf of an institution')}
          </ButtonLink>
        )}
      />
      {sum.data && (
        <div className="mb-7 grid grid-cols-2 gap-x-6 gap-y-5 md:grid-cols-3 xl:grid-cols-6">
          <Stat label={t('Held as security')} value={fmtNumber(k.held)} hint={fmtLakh(k.held_amount)} to="/instruments?status=HELD" />
          <Stat label={t('Maturing in 90 days')} value={fmtNumber(k.expiring_90)} hint={t('no renewal lodged yet')} tone="warning" to="/instruments?expiring_days=90" />
          <Stat label={t('Matured, not renewed')} value={fmtNumber(k.matured_unrenewed)} hint={fmtLakh(k.matured_amount)} tone="danger" to="/instruments?matured_unrenewed=true" />
          <Stat label={t('Pending scrutiny')} value={fmtNumber(k.pending_scrutiny)} hint={t('{n} awaiting the bank', { n: k.awaiting_bank ?? 0 })} to="/instruments?status=PENDING" />
          {isStaff ? (
            <>
              <Stat label={t('Fraud signals')} value={fmtNumber(k.fraud_signals)} hint={t('reused FDRs, closed at bank')} tone={k.fraud_signals ? 'danger' : 'default'} to="/alerts?kind=FRAUD_SIGNAL" />
              <Stat label={t('Renewed on time')} value={fmtPct(k.renewed_on_time_pct)} hint={t('of {n} renewals, last 12 months', { n: k.renewals_closed ?? 0 })} tone="success" to="/reports?key=performance" />
            </>
          ) : (
            <Stat label={t('With discrepancies')} value={fmtNumber(k.with_discrepancies)} tone={k.with_discrepancies ? 'danger' : 'default'} to="/instruments?discrepancy=any" />
          )}
        </div>
      )}
      {isStaff && <AskPanel compact />}
      <div className="grid gap-5 xl:grid-cols-2">
        {my.data!.queues.map((q) => <QueueBlock key={q.key} q={q} />)}
      </div>
      {isStaff && sum.data && sum.data.watch.at_risk.length > 0 && (
        <section className="sheet mt-5">
          <div className="flex items-baseline justify-between border-b border-slate-200 px-4 py-3">
            <div>
              <h2 className="text-[19px] font-semibold text-brand-900">{t('Likely to renew late')}</h2>
              <p className="text-[13px] text-slate-500">{t('Maturing within 120 days, predicted from each institution’s renewal history. Follow up before they lapse.')}</p>
            </div>
            <Link to="/instruments?at_risk=true&sort=risk" className="flex items-center gap-1 text-[14px] text-brand-700 hover:underline">
              {t('All')} <ArrowRight className="size-3.5" />
            </Link>
          </div>
          {sum.data.watch.at_risk.map((x) => <InstrumentLine key={x.id} x={x} right={<RiskStrip value={x.renewal_risk} />} />)}
        </section>
      )}
    </div>
  )
}
