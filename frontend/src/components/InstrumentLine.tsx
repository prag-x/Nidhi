import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { fmtDate, fmtLakh } from '@/lib/format'
import type { InstrumentItem } from '@/lib/types'
import { MaturityBadge, RefNo, StatusBadge } from './ui'

/** One deposit on one line: reference, institution, bank, amount, maturity and status. */
export default function InstrumentLine({ x, right }: { x: InstrumentItem; right?: ReactNode }) {
  return (
    <Link to={`/instruments/${x.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-slate-100 px-4 py-2.5 last:border-0 hover:bg-slate-50">
      <RefNo>{x.ref_no}</RefNo>
      <span className="min-w-[14rem] flex-1">
        <span className="block truncate text-[15px] text-brand-900">{x.institution.name}, {x.institution.city}</span>
        <span className="text-[13px] text-slate-500">
          {x.bank?.short_name ?? x.bank_name_raw} · <span className="tabular">{x.fdr_number}</span> · {fmtDate(x.maturity_date)}
        </span>
      </span>
      <span className="figure shrink-0 text-right text-[16px] text-brand-900">{fmtLakh(x.amount)}</span>
      <span className="flex shrink-0 flex-wrap justify-end gap-1">
        {right ?? (
          <>
            <StatusBadge status={x.status} />
            <MaturityBadge days={x.days_to_maturity} status={x.status} />
          </>
        )}
      </span>
    </Link>
  )
}
