import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'
import { Button, Card, CardHeader, ErrorState, Loading, PageHeader, Stat } from '@/components/ui'
import { api, errorMessage } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDateTime, fmtNumber, fmtPct } from '@/lib/format'
import { useMeta } from '@/lib/hooks'
import { t } from '@/lib/i18n'

interface Proof {
  evaluation: {
    checks: { cases: number; precision: number; recall: number; clean_cases: number; clean_flagged: number; by_fault: Record<string, { cases: number; caught: number; false_alarms: number }> }
    reader: { documents: number; layouts: number; field_accuracy: number; documents_fully_read: number; by_field: Record<string, number> }
    scanned?: { documents: number; layouts: number; field_accuracy: number; documents_fully_read: number; by_field: Record<string, number> }
    run_at: string
  } | null
  model: { trained: boolean; auc?: number; average_precision?: number; base_rate?: number; precision_top_decile?: number; holdout_instruments?: number; holdout_institutions?: number; train_instruments?: number; trained_at?: string; method?: string }
  data: Record<string, number | boolean>
  ledger: { entries: number; last_checkpoint: { seq: number; at: string; hash: string } | null }
  tests: { backend_tests: number; browser_tests: number; databases: string[] }
  models: { name: string; method: string; runs: string; data_sent_outside: boolean }[]
  external_services: string[]
}
interface Context { quotes: { text: string; source: string }[]; disclaimer: string }

const FIELD: Record<string, string> = {
  fdr_number: 'FDR number', amount: 'Amount', issue_date: 'Issue date', maturity_date: 'Maturity date',
  depositor_name: 'Depositor', lien_holder: 'Lien holder',
}

export default function Proof() {
  const { user } = useAuth()
  const meta = useMeta()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['proof'], queryFn: () => api.get<Proof>('/intelligence/proof') })
  const ctx = useQuery({ queryKey: ['context'], queryFn: () => api.get<Context>('/intelligence/context'), staleTime: Infinity })
  const verify = useQuery({ queryKey: ['proof', 'verify'], queryFn: () => api.get<{ valid: boolean; ledger_entries: number; instruments_checked: number; seconds: number }>('/intelligence/proof/verify'), enabled: false })
  const rerun = useMutation({
    mutationFn: () => api.post('/intelligence/proof/evaluate'),
    onSuccess: () => { toast.success(t('Measured again on fresh test cases')); qc.invalidateQueries({ queryKey: ['proof'] }) },
    onError: (e) => toast.error(errorMessage(e)),
  })
  if (q.isLoading) return <Loading />
  if (q.error) return <ErrorState error={q.error} retry={q.refetch} />
  const p = q.data!
  const c = p.evaluation?.checks
  const r = p.evaluation?.reader
  const m = p.model
  const titleOf = (code: string) => meta.data?.checks.find((x) => x.code === code)?.title ?? (code === 'CLEAN' ? 'No fault (clean)' : code)
  return (
    <div>
      <PageHeader
        title={t('Proof')}
        subtitle={t('What the portal claims about itself, measured on this server. Re-run any measurement and the numbers here change with it.')}
        actions={user?.role === 'ADMIN' && <Button onClick={() => rerun.mutate()} loading={rerun.isPending}>{t('Measure again')}</Button>}
      />
      {c && r && (
        <div className="mb-8 grid grid-cols-2 gap-x-6 gap-y-6 md:grid-cols-3 xl:grid-cols-6">
          <Stat label={t('Discrepancy checks: precision')} value={fmtPct(c.precision * 100)} hint={t('of faults raised, share that were real')} tone="success" />
          <Stat label={t('Discrepancy checks: recall')} value={fmtPct(c.recall * 100)} hint={t('of {n} planted faults, share caught', { n: fmtNumber(c.cases - c.clean_cases) })} tone="success" />
          <Stat label={t('Clean deposits wrongly flagged')} value={`${c.clean_flagged} / ${c.clean_cases}`} />
          <Stat label={t('Document reader')} value={fmtPct(r.field_accuracy * 100)} hint={p.evaluation?.scanned
            ? t('{n} digital FDRs; {s} on {m} scanned copies by OCR', { n: r.documents, s: fmtPct(p.evaluation.scanned.field_accuracy * 100), m: p.evaluation.scanned.documents })
            : t('of fields read correctly, {n} FDRs in {k} layouts', { n: r.documents, k: r.layouts })} />
          <Stat label={t('Late-renewal model')} value={m.auc ? m.auc.toFixed(2) : '—'} hint={t('AUC on {n} instruments of institutions it never saw', { n: m.holdout_instruments ?? 0 })} />
          <Stat label={t('Top 10% flagged, late')} value={m.precision_top_decile != null ? fmtPct(m.precision_top_decile * 100, 0) : '—'} hint={t('against a base rate of {n}', { n: m.base_rate != null ? fmtPct(m.base_rate * 100, 0) : '—' })} />
        </div>
      )}
      <div className="grid gap-5 xl:grid-cols-2">
        {c && (
          <Card>
            <CardHeader title={t('Discrepancy checks, fault by fault')}
              subtitle={t('{n} fresh deposits lodged against real institutions and banks in the database, each with one planted fault or none, checked exactly as in production and then rolled back. Run {d}.', { n: c.cases, d: fmtDateTime(p.evaluation!.run_at) })} />
            <table className="w-full text-[14px]">
              <thead>
                <tr className="border-b border-slate-200 text-left text-[12.5px] text-slate-500">
                  <th className="px-4 py-2 font-normal">{t('Planted fault')}</th>
                  <th className="px-3 py-2 text-right font-normal">{t('Cases')}</th>
                  <th className="px-3 py-2 text-right font-normal">{t('Caught')}</th>
                  <th className="px-4 py-2 text-right font-normal">{t('False alarms')}</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(c.by_fault).map(([k, v]) => (
                  <tr key={k} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-1.5">{t(titleOf(k))}</td>
                    <td className="figure px-3 py-1.5 text-right">{v.cases}</td>
                    <td className={clsx('figure px-3 py-1.5 text-right', k !== 'CLEAN' && v.caught < v.cases && 'text-seal-600')}>{k === 'CLEAN' ? '—' : v.caught}</td>
                    <td className={clsx('figure px-4 py-1.5 text-right', v.false_alarms ? 'text-seal-600' : 'text-slate-400')}>{v.false_alarms}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
        <div className="space-y-5">
          {r && (
            <Card>
              <CardHeader title={t('Reading the FDR copy')} subtitle={t('{n} specimen FDRs with random values in {k} different bank layouts; each field compared with the truth.', { n: r.documents, k: r.layouts })} />
              <dl className="grid grid-cols-2 gap-x-4 px-4 py-3 sm:grid-cols-3">
                {Object.entries(r.by_field).map(([f, v]) => (
                  <div key={f} className="py-1">
                    <dt className="text-[13px] text-slate-500">{t(FIELD[f] ?? f)}</dt>
                    <dd className="figure text-[18px] text-brand-900">{fmtPct(v * 100)}</dd>
                  </div>
                ))}
              </dl>
              {p.evaluation?.scanned && (
                <p className="border-t border-slate-100 px-4 py-2 text-[14px] text-slate-700">
                  {t('Scanned copies (200 dpi images, skewed and blurred) read by Tesseract OCR on this server: {a} of fields correct on {n} copies.', { a: fmtPct(p.evaluation.scanned.field_accuracy * 100), n: p.evaluation.scanned.documents })}
                </p>
              )}
              <p className="border-t border-slate-100 px-4 py-2 text-[13px] text-slate-500">{t('All specimens are generated by the portal. Real bank paper varies more; the officer still checks the copy and the bank still confirms.')}</p>
            </Card>
          )}
          <Card>
            <CardHeader title={t('Late-renewal prediction')} subtitle={m.method} />
            {m.trained ? (
              <p className="px-4 py-3 text-[14.5px] leading-relaxed text-slate-700">
                {t('Trained on {n} settled renewals; tested on {h} instruments from {k} institutions held out entirely. AUC {auc}; average precision {ap} against a base rate of {br}.', {
                  n: fmtNumber(m.train_instruments), h: fmtNumber(m.holdout_instruments), k: fmtNumber(m.holdout_institutions),
                  auc: m.auc?.toFixed(2) ?? '—', ap: m.average_precision?.toFixed(2) ?? '—', br: m.base_rate?.toFixed(2) ?? '—',
                })}{' '}
                {t('It ranks which deposits to chase first; it never decides anything.')}
              </p>
            ) : <p className="px-4 py-3 text-slate-500">{t('Not trained yet.')}</p>}
          </Card>
          <Card>
            <CardHeader title={t('Integrity')} icon={<ShieldCheck className="size-4.5" />} actions={<Button size="xs" onClick={() => verify.refetch()} loading={verify.isFetching}>{t('Verify now')}</Button>} />
            <p className="px-4 py-3 text-[14.5px] text-slate-700">
              {verify.data
                ? verify.data.valid
                  ? t('All {n} ledger entries and {k} deposit histories re-computed in {s} s. Nothing altered.', { n: fmtNumber(verify.data.ledger_entries), k: fmtNumber(verify.data.instruments_checked), s: verify.data.seconds })
                  : t('Verification failed: the records were altered outside the portal.')
                : t('{n} sealed ledger entries. Last checkpoint #{c}.', { n: fmtNumber(p.ledger.entries), c: p.ledger.last_checkpoint?.seq ?? '—' })}
            </p>
          </Card>
        </div>
        <Card>
          <CardHeader title={t('What runs where')} subtitle={t('No outside AI or analytics service is called. Nothing leaves this server.')} />
          <ul className="divide-y divide-slate-100">
            {p.models.map((x) => (
              <li key={x.name} className="px-4 py-2.5">
                <div className="text-[15px] font-semibold text-brand-900">{t(x.name)}</div>
                <div className="text-[13.5px] text-slate-600">{t(x.method)}</div>
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <CardHeader title={t('The data behind these numbers')} subtitle={ctx.data?.disclaimer} />
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 px-4 py-3 sm:grid-cols-3">
            {[['institutions', 'Institutions with deposits'], ['instruments', 'Instruments'], ['events', 'History entries'],
              ['documents', 'Documents'], ['letters', 'Letters issued'], ['discrepancies', 'Discrepancies raised'],
              ['banks', 'Banks'], ['bank_records', 'Bank records (simulated)'], ['regions', 'Regional Offices']].map(([k, label]) => (
              <div key={k}>
                <dt className="text-[13px] text-slate-500">{t(label)}</dt>
                <dd className="figure text-[18px] text-brand-900">{fmtNumber(Number(p.data[k] ?? 0))}</dd>
              </div>
            ))}
          </dl>
          <p className="border-t border-slate-100 px-4 py-2 text-[13px] text-slate-500">
            {t('{b} backend tests and {e} browser tests, on {d}.', { b: p.tests.backend_tests, e: p.tests.browser_tests, d: p.tests.databases.join(' and ') })}
          </p>
        </Card>
        {ctx.data && (
          <Card className="xl:col-span-2">
            <CardHeader title={t('What the problem statement asks for')} />
            <ul className="divide-y divide-slate-100">
              {ctx.data.quotes.map((x) => (
                <li key={x.text} className="px-4 py-3">
                  <blockquote className="text-[15px] leading-relaxed text-slate-800">“{x.text}”</blockquote>
                  <cite className="text-[13px] text-slate-500 not-italic">{x.source}</cite>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </div>
  )
}
