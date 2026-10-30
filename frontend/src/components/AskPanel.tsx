import { useMutation, useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { ArrowRight, CornerDownLeft, MessageSquareText } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import InstrumentLine from './InstrumentLine'
import { api, errorMessage } from '@/lib/api'
import { fmtLakh, fmtNumber } from '@/lib/format'
import { isHindi, t } from '@/lib/i18n'
import type { InstrumentItem } from '@/lib/types'
import { RiskStrip } from './Risk'
import { ButtonLink } from './ui'

interface Chip { param: string; value: string | number; label: string; label_hi: string }
interface Answer {
  question: string
  understood: Chip[]
  intent: 'list' | 'count'
  total: number | null
  amount: number | null
  items: InstrumentItem[]
  link: string | null
  examples?: string[]
}

/**
 * Ask the portal. The question is read on our own server into the same filters the Deposits page uses, so the
 * answer and "see all" always agree. What was understood is shown as chips.
 */
export default function AskPanel({ compact = false }: { compact?: boolean }) {
  const [q, setQ] = useState('')
  const examples = useQuery({ queryKey: ['ask-examples'], queryFn: () => api.get<string[]>('/ask/examples'), staleTime: Infinity })
  const ask = useMutation({ mutationFn: (question: string) => api.post<Answer>('/ask', { question }) })
  const run = (question: string) => {
    const s = question.trim()
    if (s.length < 2) return
    setQ(s)
    ask.mutate(s)
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    run(q)
  }
  const a = ask.data
  const shownExamples = (examples.data ?? []).filter((x) => (isHindi ? /[ऀ-ॿ]/.test(x) : true)).slice(0, compact ? 3 : 8)

  return (
    <section className={clsx('rounded-[6px] border border-slate-300 bg-white', compact ? 'mb-6' : '')}>
      <form onSubmit={submit} className="flex items-center gap-3 px-4 py-3">
        <MessageSquareText className="size-5 shrink-0 text-brand-700" aria-hidden />
        <label className="sr-only" htmlFor="ask-input">{t('Ask the portal')}</label>
        <input
          id="ask-input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          maxLength={300}
          placeholder={t('Ask about deposits, in English or Hindi. For example: FDRs maturing in 30 days')}
          className="min-w-0 flex-1 bg-transparent text-[16px] text-slate-900 outline-none placeholder:text-slate-400"
        />
        <button
          type="submit"
          disabled={q.trim().length < 2 || ask.isPending}
          className="inline-flex items-center gap-1.5 rounded-[5px] bg-brand-800 px-3 py-1.5 text-[14px] font-semibold text-white hover:bg-brand-900 disabled:opacity-50"
        >
          {ask.isPending ? t('Reading…') : t('Ask')} <CornerDownLeft className="size-3.5" />
        </button>
      </form>
      {!a && shownExamples.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 px-4 py-2.5 text-[13px]">
          <span className="text-slate-500">{t('Try')}</span>
          {shownExamples.map((x) => (
            <button key={x} onClick={() => run(x)} className="rounded-[4px] bg-slate-50 px-2 py-0.5 text-brand-800 ring-1 ring-slate-200 hover:bg-white">
              {x}
            </button>
          ))}
        </div>
      )}
      {ask.error && <p className="border-t border-slate-100 px-4 py-3 text-[14px] text-seal-700">{errorMessage(ask.error)}</p>}
      {a && (
        <div className="border-t border-slate-200">
          {a.total === null ? (
            <div className="px-4 py-3 text-[14px] text-slate-600">
              {t("I couldn't find a maturity window, status, bank, amount, place or institution in that question. Try one of these:")}
              <div className="mt-2 flex flex-wrap gap-2">
                {(a.examples ?? []).slice(0, 5).map((x) => (
                  <button key={x} onClick={() => run(x)} className="rounded-[4px] bg-slate-50 px-2 py-0.5 text-[13px] text-brand-800 ring-1 ring-slate-200 hover:bg-white">{x}</button>
                ))}
              </div>
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
                <span className="text-[13px] text-slate-500">{t('Read as')}</span>
                {a.understood.map((c) => (
                  <span key={c.param} className="rounded-[4px] bg-brand-50 px-2 py-0.5 text-[13px] font-semibold text-brand-800 ring-1 ring-brand-100">
                    {isHindi ? t(c.label_hi) : c.label}
                  </span>
                ))}
              </div>
              <div className="flex flex-wrap items-end justify-between gap-3 px-4 pb-3">
                <div>
                  <div className="figure text-[34px] leading-none font-semibold text-brand-900">{fmtNumber(a.total)}</div>
                  <div className="mt-1 text-[14px] text-slate-600">
                    {t(a.total === 1 ? 'matching deposit' : 'matching deposits')}
                    {a.amount ? <> · <span className="figure">{fmtLakh(a.amount)}</span></> : null}
                  </div>
                </div>
                {a.link && a.total > 0 && (
                  <ButtonLink to={a.link} size="sm" icon={<ArrowRight className="size-4" />}>{t('See them all')}</ButtonLink>
                )}
              </div>
              {a.items.length > 0 && (
                <div className="border-t border-slate-100">
                  {a.items.slice(0, compact ? 5 : 8).map((c) => (
                    <InstrumentLine key={c.id} x={c} right={a.understood.some((x) => x.param === 'at_risk') ? <RiskStrip value={c.renewal_risk} /> : undefined} />
                  ))}
                </div>
              )}
              <p className="border-t border-slate-100 px-4 py-2 text-[12.5px] text-slate-500">
                {t('Read on this server using the portal’s own lists of banks, regions, states and institutions. No question is sent to an outside AI service.')}
              </p>
            </>
          )}
        </div>
      )}
    </section>
  )
}
