import { keepPreviousData, useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { CalendarRange, Download, FileSpreadsheet, FileText, Printer } from 'lucide-react'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Button, Card, ErrorState, Field, Input, Loading, PageHeader, Select } from '@/components/ui'
import { download, api, errorMessage } from '@/lib/api'
import { fmtNumber, isoDaysAgo, todayIso } from '@/lib/format'
import { useMeta } from '@/lib/hooks'
import type { ReportOut as Report } from '@/lib/types'
type ReportColumn = Report['columns'][number]
import { t } from '@/lib/i18n'

const REPORTS = [
  { key: 'maturity', title: 'Maturity calendar', text: 'What matures in each of the next 12 months, and how much is renewed' },
  { key: 'pending', title: 'Pending scrutiny and verification', text: 'Every deposit not yet accepted, oldest first, with the bank’s position' },
  { key: 'discrepancies', title: 'Discrepancies', text: 'Open, resolved and waived, by check' },
  { key: 'status', title: 'Status-wise', text: 'Instruments and amounts at each stage' },
  { key: 'banks', title: 'Bank-wise', text: 'Holdings, verification channel, mismatches and time to verify' },
  { key: 'regions', title: 'Region-wise', text: 'Held, expiring, matured and pending by Regional Office' },
  { key: 'releases', title: 'Release register', text: 'Every release or refund request and how long it took' },
  { key: 'performance', title: 'Monthly performance', text: 'Lodged, accepted, time to accept, renewals on time, releases' },
]

function cell(value: string | number | null | undefined, col: ReportColumn) {
  if (value === null || value === undefined || value === '') return '—'
  if (col.kind === 'pct') return `${Number(value).toFixed(1)}%`
  if (col.kind === 'float') return Number(value).toFixed(1)
  if (col.kind === 'int') return fmtNumber(Number(value))
  return String(value)
}

export default function Reports() {
  const meta = useMeta()
  const [sp] = useSearchParams()
  const [key, setKey] = useState(sp.get('key') ?? 'maturity')
  const [from, setFrom] = useState(isoDaysAgo(365))
  const [to, setTo] = useState(todayIso())
  const [bank, setBank] = useState('')
  const [region, setRegion] = useState('')
  const params = { date_from: from, date_to: to, bank_id: bank || undefined, region_id: region || undefined }
  const { data, error, isFetching, refetch } = useQuery({
    queryKey: ['report', key, params],
    queryFn: () => api.get<Report>(`/reports/${key}`, params),
    placeholderData: keepPreviousData,
  })
  const exportAs = async (format: 'xlsx' | 'pdf' | 'csv') => {
    try {
      await download(`/reports/${key}`, { ...params, format }, `${key}-report.${format}`)
      toast.success('Report downloaded')
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }
  const numeric = data?.columns.filter((c) => c.kind !== 'text' && c.kind !== 'date') ?? []

  return (
    <div>
      <PageHeader title={t('Reports')} subtitle={t('Generated from live records; the same numbers in Excel, PDF and CSV. The period applies to the release register and monthly performance.')} />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-4">
        <div className="space-y-2">
          {REPORTS.map((r) => (
            <button
              key={r.key}
              onClick={() => setKey(r.key)}
              className={clsx('w-full rounded-[6px] border px-4 py-3 text-left transition-colors', key === r.key ? 'border-brand-300 bg-brand-50 ring-1 ring-brand-200' : 'border-slate-200 bg-white hover:bg-slate-50')}
            >
              <div className={clsx('text-sm font-semibold', key === r.key ? 'text-brand-900' : 'text-slate-800')}>{t(r.title)}</div>
              <div className="mt-0.5 text-xs text-slate-500">{t(r.text)}</div>
            </button>
          ))}
        </div>
        <div className="space-y-4 xl:col-span-3">
          <Card className="p-4">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Field label={t('From')}><Input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} /></Field>
              <Field label={t('To')}><Input type="date" value={to} min={from} max={todayIso()} onChange={(e) => setTo(e.target.value)} /></Field>
              <Field label={t('Bank')}>
                <Select value={bank} onChange={(e) => setBank(e.target.value)}>
                  <option value="">{t('All')}</option>
                  {meta.data?.banks.map((b) => <option key={b.id} value={b.id}>{b.short_name}</option>)}
                </Select>
              </Field>
              <Field label={t('Region')}>
                <Select value={region} onChange={(e) => setRegion(e.target.value)}>
                  <option value="">{t('All')}</option>
                  {meta.data?.regions.map((r) => <option key={r.id} value={r.id}>{r.code}</option>)}
                </Select>
              </Field>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="mr-auto inline-flex items-center gap-1.5 text-xs text-slate-500">
                <CalendarRange className="size-3.5" /> Quick:
                {[30, 90, 365].map((d) => (
                  <button key={d} className="rounded px-1.5 py-0.5 hover:bg-slate-100" onClick={() => { setFrom(isoDaysAgo(d)); setTo(todayIso()) }}>
                    {d === 365 ? '1 year' : `${d} days`}
                  </button>
                ))}
                <button className="rounded px-1.5 py-0.5 hover:bg-slate-100" onClick={() => { const y = new Date().getMonth() >= 3 ? new Date().getFullYear() : new Date().getFullYear() - 1; setFrom(`${y}-04-01`); setTo(todayIso()) }}>
                  {t('This financial year')}
                </button>
              </span>
              <Button size="sm" icon={<FileSpreadsheet className="size-4" />} onClick={() => exportAs('xlsx')}>{t('Excel')}</Button>
              <Button size="sm" icon={<FileText className="size-4" />} onClick={() => exportAs('pdf')}>{t('PDF')}</Button>
              <Button size="sm" icon={<Download className="size-4" />} onClick={() => exportAs('csv')}>{t('CSV')}</Button>
              <Button size="sm" variant="ghost" icon={<Printer className="size-4" />} onClick={() => window.print()}>{t('Print')}</Button>
            </div>
          </Card>

          <Card>
            {error ? (
              <ErrorState error={error} retry={refetch} />
            ) : !data ? (
              <Loading />
            ) : (
              <div className={clsx(isFetching && 'opacity-60')}>
                <div className="border-b border-slate-100 px-4 py-3">
                  <h2 className="text-[19px] font-semibold text-brand-900">{data.title}</h2>
                  <p className="text-[13px] text-slate-500">{data.subtitle}.{data.columns.length > 7 && ' Scroll sideways for every column; the first column stays in place.'}</p>
                </div>
                <div className="max-h-[65vh] overflow-auto">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 z-10 bg-slate-50">
                      <tr className="text-left text-xs font-medium text-slate-500">
                        {data.columns.map((c, ci) => (
                          <th key={c.key} className={clsx('border-b border-slate-200 px-3 py-2.5 whitespace-nowrap', numeric.includes(c) && 'text-right', ci === 0 && 'sticky left-0 z-20 bg-slate-50 shadow-[1px_0_0_#dadfe2]')}>{c.label}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {data.rows.map((r, i) => (
                        <tr key={i} className="hover:bg-slate-50/70">
                          {data.columns.map((c, ci) => (
                            <td key={c.key} className={clsx('px-3 py-2', numeric.includes(c) ? 'text-right whitespace-nowrap tabular' : 'min-w-44 text-slate-800', ci === 0 && 'sticky left-0 z-10 bg-white shadow-[1px_0_0_#dadfe2]')}>{cell(r[c.key], c)}</td>
                          ))}
                        </tr>
                      ))}
                      {data.totals && (
                        <tr className="bg-slate-50 font-semibold">
                          {data.columns.map((c, ci) => (
                            <td key={c.key} className={clsx('border-t border-slate-200 px-3 py-2', numeric.includes(c) && 'text-right tabular', ci === 0 && 'sticky left-0 bg-slate-50')}>{cell(data.totals![c.key], c)}</td>
                          ))}
                        </tr>
                      )}
                    </tbody>
                  </table>
                  {!data.rows.length && <p className="p-6 text-center text-sm text-slate-500">{t('No records for the selected filters.')}</p>}
                </div>
                {data.notes.length > 0 && (
                  <div className="border-t border-slate-100 px-4 py-2.5 text-xs text-slate-500">{data.notes.join(' ')}</div>
                )}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
