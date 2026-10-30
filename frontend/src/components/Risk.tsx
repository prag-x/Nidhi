import clsx from 'clsx'
import type { Driver } from '@/lib/types'
import { t } from '@/lib/i18n'

export function riskTone(p: number | null | undefined) {
  if (p === null || p === undefined) return { text: 'text-slate-400', bar: 'bg-slate-300', label: t('Not scored') }
  if (p >= 0.7) return { text: 'text-seal-600', bar: 'bg-seal-500', label: t('Likely to renew late') }
  if (p >= 0.45) return { text: 'text-turmeric-700', bar: 'bg-turmeric-400', label: t('Some risk of delay') }
  return { text: 'text-ink-green-700', bar: 'bg-ink-green-500', label: t('Usually renews on time') }
}

/** Ten-cell strip: reads at a glance in a table row without a chart. */
export function RiskStrip({ value, className }: { value: number | null | undefined; className?: string }) {
  const tone = riskTone(value)
  const filled = value === null || value === undefined ? 0 : Math.max(1, Math.round(value * 10))
  return (
    <span className={clsx('inline-flex items-center gap-2', className)} title={value != null ? t('{n}% predicted chance the replacement arrives after maturity', { n: Math.round(value * 100) }) : t('Not scored')}>
      <span className="inline-flex gap-[2px]" aria-hidden>
        {Array.from({ length: 10 }, (_, i) => (
          <span key={i} className={clsx('h-3 w-[5px] rounded-[1px]', i < filled ? tone.bar : 'bg-slate-200')} />
        ))}
      </span>
      <span className={clsx('figure text-[15px] font-semibold', tone.text)}>{value != null ? `${Math.min(99, Math.round(value * 100))}%` : '—'}</span>
    </span>
  )
}

export function RenewalRiskPanel({ risk, drivers }: { risk: number | null; drivers: Driver[] }) {
  if (risk === null || risk === undefined) return null
  const tone = riskTone(risk)
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className={clsx('text-[15px] font-semibold', tone.text)}>{tone.label}</span>
        <RiskStrip value={risk} />
      </div>
      <p className="mt-1 text-[13px] text-slate-500">{t('Chance that the replacement FDR is lodged after this one matures, judged 60 days ahead.')}</p>
      {drivers.length > 0 && (
        <ul className="mt-2 space-y-1.5">
          {drivers.map((d) => (
            <li key={d.factor} className="flex items-baseline gap-2 text-[14px] text-slate-700">
              <span className="figure w-12 shrink-0 text-right text-seal-600">+{Math.round(d.impact * 100)}</span>
              <span>{d.text}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
