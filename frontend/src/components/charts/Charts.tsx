import {
  Area,
  AreaChart,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,

} from 'recharts'
import { fmtLakh, fmtNumber } from '@/lib/format'

/** Categorical slots in fixed order (validated for colour-vision deficiency). */
export const SERIES = ['#123f3c', '#c98a0c', '#58408f', '#74b0aa', '#b8322a', '#6b5523', '#468f88', '#a48fd6']
export const STATUS_COLORS = { good: '#58408f', warning: '#e0a526', serious: '#c98a0c', critical: '#b8322a' }
/** Sequential blue ramp (light → dark) for magnitude. */
export const SEQ_TEAL = ['#ecf4f3', '#d5e7e5', '#bfdbd8', '#a9cfcb', '#8fc0ba', '#74b0aa', '#5d9f98', '#468f88', '#36807a', '#2c746e', '#1f5f5a', '#184e4a', '#123f3c']

const AXIS = { fontSize: 12, fill: '#66707c', fontFamily: 'Mukta' }
const GRID = '#e3e7e9'

function TooltipBox({ title, rows }: { title: string; rows: { label: string; value: string; color?: string }[] }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 font-semibold text-slate-800">{title}</div>
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-2 py-0.5 text-slate-600">
          {r.color && <span className="size-2.5 rounded-sm" style={{ background: r.color }} />}
          <span className="flex-1">{r.label}</span>
          <span className="font-medium text-slate-900 tabular">{r.value}</span>
        </div>
      ))}
    </div>
  )
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
      {items.map((i) => (
        <span key={i.label} className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: i.color }} />
          {i.label}
        </span>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------- maturity calendar

const MONTH = (iso: string) => new Date(iso + (iso.length === 7 ? '-01' : '') + 'T00:00:00').toLocaleDateString('en-IN', { month: 'short', year: '2-digit' })

export const MATURITY_SERIES = [
  { key: 'lodged', label: 'Renewal already lodged', color: '#a9c4c0' },
  { key: 'rest', label: 'Not yet lodged', color: '#1f5f5a' },
  { key: 'risk', label: 'Not lodged, likely late', color: '#a63d33' },
] as const
const AMOUNT_LINE = '#5b6775'

export function MaturityChart({
  data,
  onSelect,
}: {
  data: { month: string; count: number; amount: number; renewal_lodged: number; high_risk: number }[]
  onSelect?: (month: string) => void
}) {
  const rows = data.map((d) => ({
    ...d, label: MONTH(d.month), lodged: d.renewal_lodged, risk: d.high_risk,
    rest: Math.max(0, d.count - d.renewal_lodged - d.high_risk), lakh: Math.round(d.amount / 1e5),
  }))
  const total = rows.reduce((a, r) => a + r.count, 0)
  const peak = rows.reduce((m, r) => (r.count > m.count ? r : m), rows[0] ?? { count: 0, label: '' })
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Legend items={[...MATURITY_SERIES.map((s) => ({ label: s.label, color: s.color })), { label: 'Amount maturing, ₹ lakh (right scale)', color: AMOUNT_LINE }]} />
        {total > 0 && <span className="text-[12.5px] text-slate-500">{fmtNumber(total)} in 12 months · busiest {peak.label}</span>}
      </div>
      <div className="mt-3 h-64">
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 20, right: 4, left: -16, bottom: 0 }} barCategoryGap="28%">
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={{ stroke: '#d8dfdd' }} />
            <YAxis yAxisId="n" tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
            <YAxis yAxisId="amt" orientation="right" tick={AXIS} tickLine={false} axisLine={false} width={44} />
            <Tooltip
              cursor={{ fill: 'rgba(18,63,60,0.05)' }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const r = payload[0].payload as (typeof rows)[number]
                return (
                  <TooltipBox
                    title={`${r.label}: ${fmtNumber(r.count)} maturing, ${fmtLakh(r.amount)}`}
                    rows={MATURITY_SERIES.map((s) => ({ label: s.label, color: s.color, value: fmtNumber(Number(r[s.key])) }))}
                  />
                )
              }}
            />
            {MATURITY_SERIES.map((s, i) => (
              <Bar key={s.key} yAxisId="n" dataKey={s.key} stackId="m" fill={s.color} maxBarSize={40}
                radius={i === MATURITY_SERIES.length - 1 ? [2, 2, 0, 0] : 0}
                onClick={(d) => onSelect?.((d.payload as { month: string }).month)} className={onSelect ? 'cursor-pointer' : undefined}>
                {i === MATURITY_SERIES.length - 1 && <LabelList dataKey="count" position="top" style={{ fontSize: 11.5, fill: '#374240', fontWeight: 600 }} />}
              </Bar>
            ))}
            <Line yAxisId="amt" type="linear" dataKey="lakh" stroke={AMOUNT_LINE} strokeWidth={1.5} strokeDasharray="4 3"
              dot={{ r: 2.5, fill: AMOUNT_LINE, strokeWidth: 0 }} activeDot={{ r: 4 }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- monthly flow

export function FlowChart({ data }: { data: { month: string; lodged: number; accepted: number; released: number; renewed_late: number }[] }) {
  const series = [
    { key: 'lodged', label: 'Lodged', color: '#1f5f5a' },
    { key: 'accepted', label: 'Accepted', color: '#7aa39d' },
    { key: 'renewed_late', label: 'Renewed late', color: '#a63d33' },
    { key: 'released', label: 'Released', color: '#5b6775' },
  ] as const
  const rows = data.map((d) => ({ ...d, label: MONTH(d.month) }))
  return (
    <div>
      <Legend items={series.map((s) => ({ label: s.label, color: s.color }))} />
      <div className="mt-3 h-56">
        <ResponsiveContainer>
          <AreaChart data={rows} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={{ stroke: '#d8dfdd' }} minTickGap={12} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
            <Tooltip
              cursor={{ stroke: '#8a9693', strokeDasharray: '3 3' }}
              content={({ active, payload, label }) =>
                active && payload?.length ? (
                  <TooltipBox title={String(label)} rows={series.map((s) => ({ label: s.label, color: s.color, value: fmtNumber(Number(payload.find((p) => p.dataKey === s.key)?.value ?? 0)) }))} />
                ) : null
              }
            />
            {series.map((s) => (
              <Area key={s.key} type="monotone" dataKey={s.key} stroke={s.color} strokeWidth={2.5} fill={s.color} fillOpacity={0.1} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }} />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- simple ranked bars (HTML)

export function RankedBars({
  rows,
  max,
  color = SERIES[0],
  onClick,
}: {
  rows: { key: string | number; label: string; value: number; sub?: string }[]
  max?: number
  color?: string
  onClick?: (key: string | number) => void
}) {
  const top = max ?? Math.max(1, ...rows.map((r) => r.value))
  return (
    <ul className="space-y-2.5">
      {rows.map((r) => (
        <li key={r.key}>
          <button
            type="button"
            onClick={() => onClick?.(r.key)}
            disabled={!onClick}
            className="group block w-full text-left disabled:cursor-default"
            title={`${r.label}: ${fmtNumber(r.value)}`}
          >
            <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
              <span className="truncate text-slate-700 group-hover:text-brand-800">{r.label}</span>
              <span className="shrink-0 font-semibold text-slate-900 tabular">
                {fmtNumber(r.value)}
                {r.sub && <span className="ml-1 font-normal text-slate-500">{r.sub}</span>}
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full" style={{ width: `${(100 * r.value) / top}%`, background: color }} />
            </div>
          </button>
        </li>
      ))}
    </ul>
  )
}
