import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { FlowChart, MaturityChart, RankedBars, SERIES } from '@/components/charts/Charts'
import InstrumentLine from '@/components/InstrumentLine'
import { AlertTriangle, Building, CalendarClock, FileSearch, Landmark, Siren, Stamp, TrendingUp } from 'lucide-react'
import { Card, CardHeader, ErrorState, KpiTile, Loading, NotForRole, PageHeader, Select } from '@/components/ui'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDate, fmtLakh, fmtNumber, fmtPct } from '@/lib/format'
import { useMeta } from '@/lib/hooks'
import { t } from '@/lib/i18n'
import { STATUS_HEX } from '@/lib/labels'
import type { Status } from '@/lib/types'
import type { Summary } from './Home'

function monthEnd(iso: string) {
  const d = new Date(iso + 'T00:00:00')
  d.setMonth(d.getMonth() + 1)
  d.setDate(0)
  return d.toISOString().slice(0, 10)
}

export default function Dashboard() {
  const { isStaff } = useAuth()
  const meta = useMeta()
  const navigate = useNavigate()
  const [region, setRegion] = useState('')
  const [bank, setBank] = useState('')
  const q = useQuery({
    queryKey: ['dashboard', 'summary', region, bank],
    queryFn: () => api.get<Summary>('/dashboard/summary', { region_id: region || undefined, bank_id: bank || undefined }),
  })
  if (!isStaff) return <NotForRole title={t('Overview')}>{t('The overview is for AICTE officials.')}</NotForRole>
  if (q.isLoading) return <Loading />
  if (q.error) return <ErrorState error={q.error} retry={q.refetch} />
  const s = q.data!
  const k = s.kpis
  const totalCount = s.by_status.reduce((a, b) => a + b.count, 0) || 1
  return (
    <div>
      <PageHeader
        title={t('Overview')}
        subtitle={t('Active, expiring, matured, renewed, released and pending deposits, as of {d}.', { d: fmtDate(s.as_of) })}
        actions={
          <>
            <Select value={region} onChange={(e) => setRegion(e.target.value)} className="w-auto" aria-label={t('Region')}>
              <option value="">{t('All regions')}</option>
              {meta.data?.regions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </Select>
            <Select value={bank} onChange={(e) => setBank(e.target.value)} className="w-auto" aria-label={t('Bank')}>
              <option value="">{t('All banks')}</option>
              {meta.data?.banks.map((b) => <option key={b.id} value={b.id}>{b.short_name}</option>)}
            </Select>
          </>
        }
      />
      <div className="mb-8 grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiTile tone="ink" icon={<Landmark className="size-4" />} label={t('Held as security')} value={fmtLakh(k.held_amount)}
          hint={t('{n} instruments, {m} institutions', { n: fmtNumber(k.held), m: fmtNumber(k.institutions) })} to="/instruments?status=HELD" />
        <KpiTile tone="amber" icon={<CalendarClock className="size-4" />} label={t('Maturing in 90 days')} value={fmtNumber(k.expiring_90)}
          hint={t('{a} · no renewal lodged yet', { a: fmtLakh(k.expiring_amount) })} to="/instruments?expiring_days=90&sort=maturity&order=asc" />
        <KpiTile tone="red" icon={<AlertTriangle className="size-4" />} label={t('Matured, not renewed')} value={fmtNumber(k.matured_unrenewed)}
          hint={t('{a} no longer secured', { a: fmtLakh(k.matured_amount) })} to="/instruments?matured_unrenewed=true" />
        <KpiTile tone="violet" icon={<TrendingUp className="size-4" />} label={t('Renewed on time')} value={fmtPct(k.renewed_on_time_pct)}
          meter={k.renewed_on_time_pct != null ? Number(k.renewed_on_time_pct) / 100 : null}
          hint={t('{n} renewals, last 12 months', { n: k.renewals_closed ?? 0 })} to="/reports?key=performance" />
        <KpiTile tone="red" icon={<Siren className="size-4" />} label={t('Likely to renew late')} value={fmtNumber(k.high_risk)}
          hint={t('maturing within 120 days')} to="/instruments?at_risk=true&sort=risk" />
        <KpiTile tone="teal" icon={<FileSearch className="size-4" />} label={t('Pending scrutiny')} value={fmtNumber(k.pending_scrutiny)}
          hint={t('{n} with discrepancies · {f} fraud signals', { n: k.with_discrepancies ?? 0, f: k.fraud_signals ?? 0 })} to="/instruments?status=PENDING" />
        <KpiTile tone="teal" icon={<Building className="size-4" />} label={t('Awaiting the bank')} value={fmtNumber(k.awaiting_bank)}
          hint={t('replies in {a} days online, {b} by letter (median, simulated)', { a: k.verify_days_online ?? '—', b: k.verify_days_letter ?? '—' })} to="/instruments?verification=REQUESTED" />
        <KpiTile tone="violet" icon={<Stamp className="size-4" />} label={t('Releases in progress')} value={fmtNumber(k.releases_in_progress)}
          hint={t('maker-checker, lien letter on execution')} to="/releases" />
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader title={t('Maturity calendar')} subtitle={t('Instruments AICTE holds, by month of maturity. Click a month to see them.')} actions={<Link to="/maturity" className="text-[14px] text-brand-700 hover:underline">{t('Open calendar')}</Link>} />
          <div className="p-4">
            <MaturityChart data={s.calendar} onSelect={(m) => navigate(`/instruments?maturity_from=${m}&maturity_to=${monthEnd(m)}&status=HELD&sort=maturity&order=asc`)} />
          </div>
        </Card>
        <Card>
          <CardHeader title={t('Where every instrument stands')} subtitle={t('All instruments ever lodged, by current status')} />
          <div className="px-4 py-4">
            <div className="flex h-4 overflow-hidden rounded-[3px]">
              {s.by_status.map((b) => (
                <span key={b.status} title={`${b.label}: ${b.count}`} style={{ width: `${(100 * b.count) / totalCount}%`, background: STATUS_HEX[b.status as Status] }} />
              ))}
            </div>
            <table className="mt-3 w-full text-[14px]">
              <tbody>
                {s.by_status.map((b) => (
                  <tr key={b.status} className="border-b border-slate-100 last:border-0">
                    <td className="py-1.5">
                      <Link to={`/instruments?status=${b.status}`} className="inline-flex items-center gap-2 hover:underline">
                        <span className="size-2.5 rounded-sm" style={{ background: STATUS_HEX[b.status as Status] }} />{t(b.label)}
                      </Link>
                    </td>
                    <td className="figure text-right text-brand-900">{fmtNumber(b.count)}</td>
                    <td className="figure w-28 text-right text-slate-500">{fmtLakh(b.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card>
          <CardHeader title={t('Twelve months of activity')} subtitle={t('Lodged, accepted, renewed late and released, by month')} />
          <div className="p-4"><FlowChart data={s.trend} /></div>
        </Card>
        <Card>
          <CardHeader title={t('Held, by bank')} subtitle={t('Amount AICTE holds with each bank; mismatches and unknown FDRs alongside')} />
          <div className="p-4">
            <RankedBars
              color={SERIES[0]}
              rows={s.by_bank.map((b) => ({ key: b.bank_id, label: b.name, value: Math.round(b.amount / 1e5), sub: `lakh · ${b.count}${b.problems ? ` · ${b.problems} ${t('problem')}` : ''}` }))}
              onClick={(id) => navigate(`/instruments?bank_id=${id}&status=HELD`)}
            />
          </div>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader title={t('Regional Offices')} subtitle={t('Institutions are grouped by the Regional Office of their state')} />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-[14.5px]">
              <thead>
                <tr className="border-b border-slate-200 text-left text-[12.5px] text-slate-500">
                  <th className="px-4 py-2 font-normal">{t('Region')}</th>
                  <th className="px-3 py-2 text-right font-normal">{t('Held')}</th>
                  <th className="px-3 py-2 text-right font-normal">{t('Amount')}</th>
                  <th className="px-3 py-2 text-right font-normal">{t('Maturing in 90 days')}</th>
                  <th className="px-3 py-2 text-right font-normal">{t('Matured, not renewed')}</th>
                  <th className="px-3 py-2 text-right font-normal">{t('Pending scrutiny')}</th>
                </tr>
              </thead>
              <tbody>
                {s.by_region.map((r) => (
                  <tr key={r.region_id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                    <td className="px-4 py-2"><Link to={`/instruments?region_id=${r.region_id}&status=HELD`} className="text-brand-900 hover:underline">{r.name}</Link> <span className="text-[13px] text-slate-500">{r.city}</span></td>
                    <td className="figure px-3 py-2 text-right">{fmtNumber(r.held)}</td>
                    <td className="figure px-3 py-2 text-right">{fmtLakh(r.amount)}</td>
                    <td className="figure px-3 py-2 text-right text-turmeric-700">{fmtNumber(r.expiring)}</td>
                    <td className="figure px-3 py-2 text-right text-seal-600">{fmtNumber(r.matured)}</td>
                    <td className="figure px-3 py-2 text-right">{fmtNumber(r.pending)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        {s.watch.matured.length > 0 && (
          <Card>
            <CardHeader title={t('Matured and not renewed')} subtitle={t('Oldest first. Escalated after 15 and 45 days.')} />
            {s.watch.matured.map((x) => <InstrumentLine key={x.id} x={x} />)}
          </Card>
        )}
        {s.watch.expiring.length > 0 && (
          <Card>
            <CardHeader title={t('Maturing next, no renewal yet')} />
            {s.watch.expiring.map((x) => <InstrumentLine key={x.id} x={x} />)}
          </Card>
        )}
      </div>
    </div>
  )
}
