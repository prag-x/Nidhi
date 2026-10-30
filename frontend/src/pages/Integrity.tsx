import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { ShieldAlert, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Button, Card, CardHeader, ErrorState, Loading, PageHeader, NotForRole } from '@/components/ui'
import { api, errorMessage } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDateTime, fmtNumber } from '@/lib/format'
import { useHealth } from '@/lib/hooks'
import { t } from '@/lib/i18n'

interface LedgerVerify {
  valid: boolean
  ledger_entries: number
  head_seq: number
  head_hash: string
  first_break: { seq: number; kind: string; reason: string } | null
  instruments_checked: number
  broken_instruments: { instrument_id: number; ref_no: string; broken_at_seq: number }[]
  unledgered_events: number
  seconds: number
}
interface Entry { seq: number; at: string; action: string; entity_type: string | null; entity_id: string | null; user: string; hash: string; prev_hash: string }
interface Anchor { seq: number; hash: string; at: string; note: string | null; by: string }

const ACTION_TEXT: Record<string, string> = {
  instrument_event: 'Deposit history entry sealed',
  login: 'Signed in',
  login_failed: 'Failed sign-in',
  ledger_checkpoint: 'Checkpoint published',
  instrument_submitted: 'Deposit lodged',
  instrument_accept: 'Accepted as security',
  instrument_release_execute: 'Lien released',
  instrument_release_decide: 'Release decided',
  report_exported: 'Report exported',
}

export default function Integrity() {
  const auth = useAuth()
  if (!(auth.isGlobal)) return <NotForRole title={t('Integrity')}>{t("Ledger verification is carried out by the auditor, the competent authority, the RB head and the administrator. Each deposit page still shows whether its own history is intact.")}</NotForRole>
  return <IntegrityPage />
}

function IntegrityPage() {
  const { user } = useAuth()
  const health = useHealth()
  const qc = useQueryClient()
  const verify = useQuery({ queryKey: ['ledger', 'verify'], queryFn: () => api.get<LedgerVerify>('/intelligence/ledger/verify') })
  const entries = useQuery({ queryKey: ['ledger', 'entries'], queryFn: () => api.get<Entry[]>('/intelligence/ledger/entries', { page_size: 12 }) })
  const anchors = useQuery({ queryKey: ['ledger', 'anchors'], queryFn: () => api.get<Anchor[]>('/intelligence/ledger/anchors') })
  const refresh = () => qc.invalidateQueries({ queryKey: ['ledger'] })
  const publish = useMutation({
    mutationFn: () => api.post<Anchor>('/intelligence/ledger/anchor', {}),
    onSuccess: (a) => {
      toast.success(`Checkpoint #${a.seq} published. Note its seal outside the system: ${a.hash.slice(0, 16)}…`)
      refresh()
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  const tamper = useMutation({
    mutationFn: (target: 'instrument_event' | 'ledger') => api.post<{ done: string }>('/intelligence/ledger/tamper-demo', { target }),
    onSuccess: (r) => {
      toast.warning(`${r.done} Now verify.`)
      refresh()
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  const restore = useMutation({
    mutationFn: () => api.post('/intelligence/ledger/tamper-demo/restore'),
    onSuccess: () => {
      toast.success('Original value restored')
      refresh()
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  if (verify.error) return <ErrorState error={verify.error} retry={() => verify.refetch()} />
  const v = verify.data
  const canPublish = user?.role === 'ADMIN' || user?.role === 'AUDITOR'
  return (
    <div>
      <PageHeader
        title={t('Integrity')}
        subtitle={t('Every sign-in, decision, export and deposit-history entry is sealed into one hash chain. Changing, deleting or re-ordering anything afterwards breaks the chain at that point.')}
        actions={
          <>
            <Button onClick={() => verify.refetch()} loading={verify.isFetching}>{t('Verify now')}</Button>
            {canPublish && <Button variant="primary" onClick={() => publish.mutate()} loading={publish.isPending}>{t('Publish checkpoint')}</Button>}
          </>
        }
      />
      {!v ? (
        <Loading label={t('Re-computing every seal…')} />
      ) : (
        <section className={clsx('mb-6 flex flex-col gap-4 rounded-[6px] border p-5 sm:flex-row sm:items-center', v.valid ? 'border-ink-green-100 bg-ink-green-50' : 'border-seal-100 bg-seal-50')}>
          {v.valid ? <ShieldCheck className="size-12 shrink-0 text-ink-green-600" /> : <ShieldAlert className="size-12 shrink-0 text-seal-600" />}
          <div className="min-w-0 flex-1">
            <h2 className={clsx('text-[26px] leading-tight font-semibold', v.valid ? 'text-ink-green-700' : 'text-seal-700')}>
              {v.valid ? 'Nothing has been altered' : 'Tampering detected'}
            </h2>
            <p className="mt-1 text-[15px] text-slate-700">
              {v.valid
                ? `${fmtNumber(v.ledger_entries)} ledger entries and ${fmtNumber(v.instruments_checked)} deposit histories re-computed in ${v.seconds} seconds; every seal matches, and every published checkpoint still matches.`
                : v.first_break?.reason ??
                  `${v.broken_instruments.length} deposit ${v.broken_instruments.length === 1 ? 'history does' : 'histories do'} not match their seals.`}
            </p>
            {!v.valid && v.broken_instruments.length > 0 && (
              <p className="mt-1 text-[15px] text-slate-700">
                Altered history:{' '}
                {v.broken_instruments.map((b) => (
                  <Link key={b.instrument_id} to={`/instruments/${b.instrument_id}`} className="mr-2 file-no hover:underline">{b.ref_no} entry {b.broken_at_seq}</Link>
                ))}
              </p>
            )}
            {v.unledgered_events > 0 && <p className="mt-1 text-[15px] text-seal-700">{v.unledgered_events} deposit-history entries exist that were never sealed in the ledger.</p>}
          </div>
          <div className="shrink-0 text-[13px] text-slate-600 sm:text-right">
            <div>Latest seal #{fmtNumber(v.head_seq)}</div>
            <div className="max-w-[18rem] truncate font-mono text-[12px]">{v.head_hash}</div>
          </div>
        </section>
      )}

      <div className="grid gap-5 xl:grid-cols-2">
        <Card>
          <CardHeader title={t('How the seal works')} />
          <ol className="list-decimal space-y-2 py-4 pr-5 pl-9 text-[15px] leading-relaxed text-slate-700">
            <li>Each entry stores the seal (SHA-256 hash) of the entry before it, and its own seal is computed over its contents plus that previous seal.</li>
            <li>{t('Each deposit also keeps its own chained history, and every history entry is sealed into the system ledger as it is written.')}</li>
            <li>Checkpoints copy the latest seal out of the system (printed, e-mailed or published). Even someone who rewrites the whole database cannot match an old checkpoint.</li>
          </ol>
        </Card>
        <Card>
          <CardHeader title={t('Published checkpoints')} subtitle={t('Daily, after data loads, and whenever an auditor publishes one')} />
          {anchors.data?.length ? (
            <table className="w-full text-[14px]">
              <tbody>
                {anchors.data.slice(0, 8).map((a) => (
                  <tr key={`${a.seq}-${a.at}`} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-2 whitespace-nowrap text-slate-600">{fmtDateTime(a.at)}</td>
                    <td className="figure px-2 py-2 font-semibold">#{fmtNumber(a.seq)}</td>
                    <td className="max-w-[12rem] truncate px-2 py-2 font-mono text-[12px] text-slate-500">{a.hash}</td>
                    <td className="px-4 py-2 text-slate-600">{a.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="p-4 text-slate-500">{t('No checkpoints yet.')}</p>
          )}
        </Card>
      </div>

      <Card className="mt-5">
        <CardHeader title={t('Latest ledger entries')} />
        {entries.data ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-[14px]">
              <thead>
                <tr className="border-b border-slate-200 text-left text-[13px] text-slate-500">
                  <th className="px-4 py-2 font-normal">{t('Seal')}</th>
                  <th className="px-3 py-2 font-normal">{t('When')}</th>
                  <th className="px-3 py-2 font-normal">{t('What')}</th>
                  <th className="px-3 py-2 font-normal">{t('Who')}</th>
                  <th className="px-4 py-2 font-normal">{t('Links to')}</th>
                </tr>
              </thead>
              <tbody>
                {entries.data.map((e) => (
                  <tr key={e.seq} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-2"><span className="figure font-semibold">#{fmtNumber(e.seq)}</span> <span className="font-mono text-[12px] text-slate-500">{e.hash.slice(0, 12)}</span></td>
                    <td className="px-3 py-2 whitespace-nowrap text-slate-600">{fmtDateTime(e.at)}</td>
                    <td className="px-3 py-2 text-slate-800">
                      {ACTION_TEXT[e.action] ?? (e.action.charAt(0).toUpperCase() + e.action.slice(1)).replace(/^Instrument_/, 'Deposit: ').replace(/_/g, ' ')}
                      {e.entity_type === 'instrument' && e.entity_id && <Link to={`/instruments/${e.entity_id}`} className="ml-2 text-brand-700 hover:underline">#{e.entity_id}</Link>}
                    </td>
                    <td className="px-3 py-2 text-slate-600">{e.user}</td>
                    <td className="px-4 py-2 font-mono text-[12px] text-slate-500">{e.prev_hash.slice(0, 12)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Loading />
        )}
      </Card>

      {user?.role === 'ADMIN' && health.data?.demo_mode && (
        <Card className="mt-5 border-buff-200">
          <CardHeader title={t('Demonstration: simulate an insider edit')} subtitle={t('Changes a stored value directly in the database, bypassing the application, so you can watch verification catch it. Available only in demo mode.')} />
          <div className="flex flex-wrap gap-2 p-4">
            <Button onClick={() => tamper.mutate('instrument_event')} loading={tamper.isPending}>{t('Rewrite a bank-verification record')}</Button>
            <Button onClick={() => tamper.mutate('ledger')} loading={tamper.isPending}>{t('Alter a sign-in record')}</Button>
            <Button variant="ghost" onClick={() => restore.mutate()} loading={restore.isPending}>{t('Undo the edit')}</Button>
          </div>
        </Card>
      )}
    </div>
  )
}
