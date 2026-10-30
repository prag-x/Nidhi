import { AlertTriangle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { fmtDate, fmtLakh } from '@/lib/format'
import { t } from '@/lib/i18n'
import { PURPOSE } from '@/lib/labels'
import type { InstrumentItem } from '@/lib/types'
import { RiskStrip } from './Risk'
import { EmptyState, MaturityBadge, RefNo, StatusBadge, VerificationBadge } from './ui'

export default function InstrumentTable({
  items,
  empty = t('Nothing here.'),
  showInstitution = true,
  showRisk = false,
  compact = false,
}: {
  items: InstrumentItem[]
  empty?: string
  showInstitution?: boolean
  showRisk?: boolean
  compact?: boolean
}) {
  if (!items.length) return <EmptyState title={empty} />
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] text-left text-[14.5px]">
        <thead>
          <tr className="border-b border-slate-200 text-[12.5px] text-slate-500">
            <th className="px-4 py-2 font-normal">{t('Reference')}</th>
            {showInstitution && <th className="px-3 py-2 font-normal">{t('Institution')}</th>}
            <th className="px-3 py-2 font-normal">{t('Bank and FDR')}</th>
            <th className="px-3 py-2 text-right font-normal">{t('Amount')}</th>
            <th className="px-3 py-2 font-normal">{t('Matures')}</th>
            <th className="px-3 py-2 font-normal">{t('Status')}</th>
            {showRisk && <th className="px-3 py-2 font-normal">{t('Late-renewal risk')}</th>}
          </tr>
        </thead>
        <tbody>
          {items.map((x) => (
            <tr key={x.id} className="border-b border-slate-100 align-top last:border-0 hover:bg-slate-50/70">
              <td className="px-4 py-2.5">
                <Link to={`/instruments/${x.id}`} className="hover:underline">
                  <RefNo>{x.ref_no}</RefNo>
                </Link>
                {!compact && <div className="mt-0.5 text-[12.5px] text-slate-500">{PURPOSE[x.purpose]} · {x.approval_year}</div>}
              </td>
              {showInstitution && (
                <td className="max-w-[260px] px-3 py-2.5">
                  <Link to={`/institutions/${x.institution.id}`} className="line-clamp-1 text-brand-900 hover:underline">{x.institution.name}</Link>
                  <div className="text-[12.5px] text-slate-500">{x.institution.city}</div>
                </td>
              )}
              <td className="px-3 py-2.5">
                <div className="text-slate-800">{x.bank?.short_name ?? x.bank_name_raw ?? '—'}</div>
                <div className="figure text-[13px] text-slate-500">{x.fdr_number}</div>
              </td>
              <td className="px-3 py-2.5 text-right">
                <span className="figure text-[15px] text-brand-900">{fmtLakh(x.amount)}</span>
                {x.required_amount && x.amount < x.required_amount && (
                  <div className="text-[12px] text-seal-600">{t('needs {n}', { n: fmtLakh(x.required_amount) })}</div>
                )}
              </td>
              <td className="px-3 py-2.5 whitespace-nowrap">
                <div className="tabular text-slate-700">{fmtDate(x.maturity_date)}</div>
                <MaturityBadge days={x.days_to_maturity} status={x.status} />
              </td>
              <td className="px-3 py-2.5">
                <div className="flex flex-wrap gap-1">
                  <StatusBadge status={x.status} />
                  {['SUBMITTED', 'UNDER_SCRUTINY', 'DISCREPANCY'].includes(x.status) && <VerificationBadge status={x.verification_status} />}
                </div>
                {x.open_discrepancies > 0 && (
                  <div className="mt-1 flex items-center gap-1 text-[12.5px] text-seal-600">
                    <AlertTriangle className="size-3.5" />
                    {t('{n} open discrepancy(ies)', { n: x.open_discrepancies })}
                  </div>
                )}
              </td>
              {showRisk && (
                <td className="w-40 px-3 py-2.5">
                  {x.renewal_risk !== null ? <RiskStrip value={x.renewal_risk} /> : <span className="text-slate-400">—</span>}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
