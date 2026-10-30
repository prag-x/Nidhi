import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  ArrowLeft,
  Check,
  CircleAlert,
  FileDown,
  FileUp,
  Landmark,
  Link2,
  Mail,
  QrCode,
  RefreshCcw,
  ShieldCheck,
  Stamp,
  X,
} from 'lucide-react'
import { useRef, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { RenewalRiskPanel } from '@/components/Risk'
import {
  Badge,
  Button,
  ButtonLink,
  Card,
  CardHeader,
  ErrorState,
  Field,
  Input,
  KeyValue,
  Loading,
  MaturityBadge,
  Modal,
  RefNo,
  Select,
  SeverityBadge,
  StatusBadge,
  Textarea,
  VerificationBadge,
} from '@/components/ui'
import { api, ApiError, download, errorMessage, getToken } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fileSize, fmtDate, fmtDateTime, fmtINR, fmtLakh } from '@/lib/format'
import { useMeta } from '@/lib/hooks'
import { t } from '@/lib/i18n'
import { LETTER_KIND, PURPOSE, RELEASE_STEPS } from '@/lib/labels'
import type { CompareRow, DiscrepancyOut, InstrumentDetail as Detail, LetterOut, ReleaseOut } from '@/lib/types'

type Act = (action: string, body?: Record<string, unknown>, ok?: string) => Promise<void>

function show(field: string, v: unknown): ReactNode {
  if (v === null || v === undefined || v === '') return <span className="text-slate-400">—</span>
  if (field === 'amount') return fmtINR(Number(v))
  if (field.endsWith('_date')) return fmtDate(String(v))
  return String(v)
}

function Agree({ ok }: { ok: boolean | null }) {
  if (ok === null) return null
  return ok ? <Check className="size-4 shrink-0 text-ink-green-600" aria-label={t('agrees')} /> : <X className="size-4 shrink-0 text-seal-600" aria-label={t('differs')} />
}

/** The signature view: declared, read from the document, and confirmed by the bank, field by field. */
function ThreeSources({ x }: { x: Detail }) {
  const latest = x.verifications.at(-1)
  const bankNote =
    x.verification_status === 'CONFIRMED' || x.verification_status === 'MISMATCH'
      ? `${latest?.channel === 'GATEWAY' ? t('Online, from the bank') : t('Branch reply recorded')} · ${fmtDate(latest?.responded_at)}`
      : x.verification_status === 'REQUESTED' ? t('Letter sent; reply awaited')
      : x.verification_status === 'NOT_FOUND' ? t('The bank has no such FDR') : t('Not asked yet')
  const cell = (r: CompareRow, k: 'declared' | 'document' | 'bank') => {
    const agree = k === 'document' ? r.document_agrees : k === 'bank' ? r.bank_agrees : null
    return (
      <td className={clsx('px-3 py-2 align-top', agree === false && 'bg-seal-50')}>
        <span className="flex items-start gap-1.5">
          <span className={clsx('figure text-[15px]', agree === false ? 'font-semibold text-seal-700' : k === 'bank' && agree ? 'text-ink-green-700' : 'text-brand-900')}>
            {show(r.field, r[k])}
          </span>
          <Agree ok={agree} />
        </span>
      </td>
    )
  }
  return (
    <Card>
      <CardHeader
        icon={<ShieldCheck className="size-4.5" />}
        title={t('Declared, on the document, confirmed by the bank')}
        subtitle={t('Kept apart and never overwritten. A red cell differs from what the institution declared.')}
      />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left">
          <thead>
            <tr className="border-b border-slate-200 text-[12.5px] text-slate-500">
              <th className="w-40 px-4 py-2 font-normal" />
              <th className="px-3 py-2 font-normal">
                <span className="block font-semibold text-slate-700">{t('Declared by institution')}</span>
                {fmtDate(x.submitted_at)}
              </th>
              <th className="px-3 py-2 font-normal">
                <span className="block font-semibold text-slate-700">{t('Read from FDR copy')}</span>
                {x.doc_extract ? t('{n}% of fields read', { n: Math.round((x.doc_extract_confidence ?? 0) * 100) }) : t('No copy read')}
              </th>
              <th className="px-3 py-2 font-normal">
                <span className="block font-semibold text-slate-700">{t('Confirmed by bank')}</span>
                {bankNote}
              </th>
            </tr>
          </thead>
          <tbody>
            {x.compare.map((r) => (
              <tr key={r.field} className="border-b border-slate-100 last:border-0">
                <th className="px-4 py-2 text-left text-[13.5px] font-normal text-slate-600">{t(r.label)}</th>
                {cell(r, 'declared')}
                {cell(r, 'document')}
                {cell(r, 'bank')}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function Discrepancies({ x, act }: { x: Detail; act: Act }) {
  const [resolving, setResolving] = useState<{ d: DiscrepancyOut; waive: boolean } | null>(null)
  const [note, setNote] = useState('')
  const [raising, setRaising] = useState(false)
  const [raise, setRaise] = useState({ remarks: '', severity: 'MEDIUM', field: '' })
  const open = x.discrepancies.filter((d) => d.status === 'OPEN')
  const closed = x.discrepancies.filter((d) => d.status !== 'OPEN')
  const p = x.permissions
  return (
    <Card>
      <CardHeader
        icon={<CircleAlert className="size-4.5" />}
        title={open.length ? t('{n} open discrepancy(ies)', { n: open.length }) : t('No open discrepancies')}
        subtitle={t('Checked automatically against the deposit norm, the document, the bank and every other FDR on record.')}
        actions={p.scrutinise && <Button size="xs" onClick={() => setRaising(true)}>{t('Raise one')}</Button>}
      />
      {open.length === 0 && closed.length === 0 && <p className="px-4 py-4 text-[14px] text-slate-500">{t('All checks passed.')}</p>}
      <ul>
        {open.map((d) => (
          <li key={d.id} className="border-b border-slate-100 px-4 py-3 last:border-0">
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge severity={d.severity} />
              <span className="text-[15px] font-semibold text-brand-900">{t(d.title)}</span>
              <Badge className="bg-white text-slate-500 ring-slate-200">{d.source === 'BANK' ? t('from the bank') : d.source === 'DOCUMENT' ? t('from the document') : d.source === 'OFFICER' ? t('raised by officer') : t('rule')}</Badge>
            </div>
            <p className="mt-1 text-[14px] text-slate-700">{d.message}</p>
            {(d.expected || d.found) && (
              <p className="mt-0.5 text-[13px] text-slate-500">
                {d.expected && <>{t('Expected')} <span className="figure text-slate-700">{d.expected}</span></>}
                {d.found && <> · {t('Found')} <span className="figure text-seal-700">{d.found}</span></>}
              </p>
            )}
            {d.related && (
              <p className="mt-1 text-[13px]">
                <Link to={`/instruments/${d.related.id}`} className="inline-flex items-center gap-1 text-brand-700 hover:underline">
                  <Link2 className="size-3.5" /> {d.related.ref_no}, {d.related.institution.name}, {d.related.institution.city}
                </Link>
              </p>
            )}
            {(p.scrutinise || p.waive) && (
              <div className="mt-2 flex gap-2">
                {p.scrutinise && <Button size="xs" onClick={() => { setNote(''); setResolving({ d, waive: false }) }}>{t('Mark resolved')}</Button>}
                {p.waive && <Button size="xs" variant="ghost" onClick={() => { setNote(''); setResolving({ d, waive: true }) }}>{t('Waive with reason')}</Button>}
              </div>
            )}
          </li>
        ))}
      </ul>
      {closed.length > 0 && (
        <details className="border-t border-slate-100 px-4 py-2 text-[13.5px] text-slate-600">
          <summary className="cursor-pointer">{t('{n} resolved or waived', { n: closed.length })}</summary>
          <ul className="mt-2 space-y-1.5">
            {closed.map((d) => (
              <li key={d.id}>
                <span className={d.status === 'WAIVED' ? 'text-turmeric-700' : 'text-ink-green-700'}>{d.status === 'WAIVED' ? t('Waived') : t('Resolved')}</span>
                {' · '}{t(d.title)}{d.resolution_note ? `: ${d.resolution_note}` : ''}
                {d.resolved_by && <span className="text-slate-400"> ({d.resolved_by.full_name}, {fmtDate(d.resolved_at)})</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
      <Modal
        open={!!resolving}
        onClose={() => setResolving(null)}
        title={resolving?.waive ? t('Waive discrepancy') : t('Resolve discrepancy')}
        description={resolving ? t(resolving.d.title) : undefined}
        footer={
          <Button
            variant="primary"
            disabled={note.trim().length < 10}
            onClick={async () => {
              await act(resolving!.waive ? 'waive_discrepancy' : 'resolve_discrepancy', { discrepancy_id: resolving!.d.id, remarks: note }, t('Recorded'))
              setResolving(null)
            }}
          >
            {resolving?.waive ? t('Waive') : t('Resolve')}
          </Button>
        }
      >
        <Field label={t('Reason, for the record')} hint={t('At least 10 characters. Kept in the sealed history.')}>
          <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
      </Modal>
      <Modal
        open={raising}
        onClose={() => setRaising(false)}
        title={t('Raise a discrepancy')}
        footer={
          <Button variant="primary" disabled={raise.remarks.trim().length < 5} onClick={async () => { await act('raise_discrepancy', raise, t('Raised')); setRaising(false) }}>
            {t('Raise')}
          </Button>
        }
      >
        <div className="space-y-3">
          <Field label={t('What is wrong')}>
            <Textarea rows={3} value={raise.remarks} onChange={(e) => setRaise({ ...raise, remarks: e.target.value })} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t('Severity')}>
              <Select value={raise.severity} onChange={(e) => setRaise({ ...raise, severity: e.target.value })}>
                {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((s) => <option key={s} value={s}>{s.toLowerCase()}</option>)}
              </Select>
            </Field>
            <Field label={t('Field (optional)')}>
              <Select value={raise.field} onChange={(e) => setRaise({ ...raise, field: e.target.value })}>
                <option value="" />
                {x.compare.map((r) => <option key={r.field} value={r.field}>{t(r.label)}</option>)}
              </Select>
            </Field>
          </div>
        </div>
      </Modal>
    </Card>
  )
}

function BankPanel({ x, act }: { x: Detail; act: Act }) {
  const [reply, setReply] = useState(false)
  const [found, setFound] = useState(true)
  const [vals, setVals] = useState<Record<string, string>>({})
  const [ref, setRef] = useState('')
  const pending = ['SUBMITTED', 'UNDER_SCRUTINY', 'DISCREPANCY'].includes(x.status)
  const gateway = x.bank?.verify_channel === 'GATEWAY'
  const p = x.permissions
  const openReply = () => {
    setVals(Object.fromEntries(x.compare.map((r) => [r.field, r.declared == null ? '' : String(r.declared)])))
    setFound(true)
    setRef('')
    setReply(true)
  }
  return (
    <Card>
      <CardHeader
        icon={<Landmark className="size-4.5" />}
        title={x.bank?.name ?? x.bank_name_raw ?? t('Bank not identified')}
        subtitle={[x.branch, x.ifsc].filter(Boolean).join(' · ') || undefined}
        actions={<VerificationBadge status={x.verification_status} />}
      />
      <div className="px-4 py-3 text-[14px] text-slate-600">
        {x.bank ? (
          gateway ? t('This bank confirms FDRs online through its verification service; the answer is recorded as it arrives.')
            : t('This bank confirms by letter. The portal writes the letter with a QR code; the officer records the branch’s reply.')
        ) : t('The bank could not be identified from the IFSC or name given.')}
        {x.bank && !x.bank.is_scheduled && <p className="mt-1 text-seal-700">{t('Not a scheduled commercial bank.')}</p>}
      </div>
      {(p.scrutinise && pending) || p.reverify ? (
        <div className="flex flex-wrap gap-2 border-t border-slate-100 px-4 py-3">
          {p.scrutinise && pending && (
            <Button size="sm" variant="primary" icon={gateway ? <RefreshCcw className="size-4" /> : <Mail className="size-4" />}
              onClick={() => act('verify', {}, gateway ? t('Bank answered') : t('Verification letter issued'))}>
              {gateway ? t('Verify with bank now') : t('Send verification letter')}
            </Button>
          )}
          {(p.scrutinise || p.reverify) && (x.verification_status === 'REQUESTED' || !gateway) && (
            <Button size="sm" onClick={openReply}>{t('Record bank’s reply')}</Button>
          )}
          {p.reverify && !pending && (
            <Button size="sm" icon={<RefreshCcw className="size-4" />} onClick={() => act('reverify', {}, t('Asked the bank again'))}>{t('Re-confirm with bank')}</Button>
          )}
        </div>
      ) : null}
      {x.verifications.length > 0 && (
        <ul className="border-t border-slate-100 px-4 py-2 text-[13.5px]">
          {[...x.verifications].reverse().map((v) => (
            <li key={v.id} className="flex flex-wrap items-baseline gap-x-2 py-1">
              <VerificationBadge status={v.status} />
              <span className="text-slate-600">{v.channel === 'GATEWAY' ? t('online') : v.channel === 'LETTER' ? t('by letter') : t('recorded')}</span>
              <span className="tabular text-slate-500">{fmtDateTime(v.responded_at ?? v.requested_at)}</span>
              {v.reference && <span className="text-slate-500">· {t('ref')} {v.reference}</span>}
              {v.differences && v.differences.length > 0 && (
                <span className="w-full text-seal-700">{v.differences.map((d) => `${d.field}: ${String(d.bank)}`).join('; ')}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      <Modal
        open={reply}
        onClose={() => setReply(false)}
        title={t('Record the bank’s reply')}
        description={t('Enter what the branch confirmed, not what the institution declared. Fields are pre-filled from the declaration; change any that differ.')}
        size="lg"
        footer={
          <Button variant="primary" onClick={async () => {
            await act('bank_reply', { found, bank_values: found ? vals : undefined, reference: ref || undefined }, t('Reply recorded'))
            setReply(false)
          }}>
            {t('Record reply')}
          </Button>
        }
      >
        <div className="space-y-3">
          <div className="flex gap-4 text-[14px]">
            <label className="flex items-center gap-1.5"><input type="radio" checked={found} onChange={() => setFound(true)} /> {t('Bank confirmed the FDR')}</label>
            <label className="flex items-center gap-1.5"><input type="radio" checked={!found} onChange={() => setFound(false)} /> {t('Bank has no such FDR')}</label>
          </div>
          {found && (
            <div className="grid gap-3 sm:grid-cols-2">
              {x.compare.map((r) => (
                <Field key={r.field} label={t(r.label)}>
                  <Input value={vals[r.field] ?? ''} onChange={(e) => setVals({ ...vals, [r.field]: e.target.value })} type={r.field.endsWith('_date') ? 'date' : 'text'} />
                </Field>
              ))}
            </div>
          )}
          <Field label={t('Bank’s letter reference')}>
            <Input value={ref} onChange={(e) => setRef(e.target.value)} />
          </Field>
        </div>
      </Modal>
    </Card>
  )
}

const CONDITION_HINT: Record<string, string> = {
  no_liability: 'facts.dues',
  approval_position: 'facts.approval',
}

function ReleasePanel({ x, act }: { x: Detail; act: Act }) {
  const meta = useMeta()
  const r: ReleaseOut | undefined = [...x.releases].reverse().find((r) => ['REQUESTED', 'RECOMMENDED', 'APPROVED'].includes(r.status)) ?? x.releases.at(-1)
  const facts = useQuery({
    queryKey: ['instrument', x.id, 'release-facts'],
    queryFn: () => api.get<Record<string, { ok: boolean | null; text: string }>>(`/instruments/${x.id}/release-facts`),
    enabled: !!r && r.status === 'REQUESTED' && x.permissions.recommend_release,
  })
  const [asking, setAsking] = useState(false)
  const [reason, setReason] = useState('')
  const [details, setDetails] = useState('')
  const [checks, setChecks] = useState<Record<string, { ok: boolean; note: string }>>({})
  const [note, setNote] = useState('')
  const p = x.permissions
  if (!r && !p.request_release) return null
  const stepIndex = r ? (r.status === 'REJECTED' ? -1 : RELEASE_STEPS.findIndex((s) => s.key === r.status)) : -1
  const conditions = meta.data?.release_conditions ?? []
  const allChecked = conditions.every((c) => checks[c.key]?.ok)
  return (
    <Card>
      <CardHeader icon={<Stamp className="size-4.5" />} title={t('Release or refund')}
        subtitle={t('Requested, recommended by the Regulation Bureau, approved by the competent authority, executed by Accounts. Nobody approves their own recommendation.')} />
      {r && (
        <div className="px-4 py-3">
          <div className="text-[15px] font-semibold text-brand-900">{r.reason_label}</div>
          {r.details && <p className="text-[14px] text-slate-600">{r.details}</p>}
          <ol className="mt-3 grid gap-2 sm:grid-cols-4">
            {RELEASE_STEPS.map((s, i) => {
              const who = i === 0 ? r.requested_by : i === 1 ? r.recommended_by : i === 2 ? r.approved_by : r.executed_by
              const when = i === 0 ? r.requested_at : i === 1 ? r.recommended_at : i === 2 ? r.approved_at : r.executed_at
              const done = r.status !== 'REJECTED' && i <= stepIndex
              return (
                <li key={s.key} className={clsx('border-t-2 pt-1.5 text-[13px]', done ? 'border-ink-green-600' : 'border-slate-200')}>
                  <span className={clsx('block font-semibold', done ? 'text-ink-green-700' : 'text-slate-500')}>{s.label}</span>
                  {done && who && <span className="block text-slate-600">{who.full_name}</span>}
                  {done && when && <span className="tabular text-slate-400">{fmtDate(when)}</span>}
                </li>
              )
            })}
          </ol>
          {r.status === 'REJECTED' && <p className="mt-2 text-[14px] text-seal-700">{t('Not approved')}{r.decision_note ? `: ${r.decision_note}` : ''}</p>}
          {Object.keys(r.checklist ?? {}).length > 0 && (
            <ul className="mt-3 space-y-1 text-[13.5px] text-slate-600">
              {conditions.map((c) => r.checklist[c.key] && (
                <li key={c.key} className="flex gap-1.5"><Check className="mt-0.5 size-3.5 shrink-0 text-ink-green-600" />{t(c.label)}{r.checklist[c.key].note ? ` — ${r.checklist[c.key].note}` : ''}</li>
              ))}
            </ul>
          )}
          {r.letter_code && (
            <p className="mt-3 text-[14px]">
              {t('Lien-release letter')} <Link to={`/verify/${r.letter_code}`} className="file-no">{r.letter_code}</Link>
            </p>
          )}
        </div>
      )}
      {r?.status === 'REQUESTED' && p.recommend_release && (
        <div className="border-t border-slate-100 px-4 py-3">
          <div className="mb-2 text-[14px] font-semibold text-slate-700">{t('Check each condition before recommending')}</div>
          <ul className="space-y-2">
            {conditions.map((c) => {
              const fact = facts.data?.[c.key] ?? facts.data?.[CONDITION_HINT[c.key] ?? '']
              return (
                <li key={c.key} className="text-[14px]">
                  <label className="flex items-start gap-2">
                    <input type="checkbox" className="mt-1" checked={!!checks[c.key]?.ok}
                      onChange={(e) => setChecks({ ...checks, [c.key]: { ok: e.target.checked, note: checks[c.key]?.note ?? '' } })} />
                    <span>
                      {t(c.label)}
                      {fact && <span className={clsx('block text-[13px]', fact.ok === false ? 'text-seal-700' : 'text-slate-500')}>{t('Portal found')}: {fact.text}</span>}
                    </span>
                  </label>
                </li>
              )
            })}
          </ul>
          <Textarea className="mt-2" rows={2} placeholder={t('Note for the competent authority')} value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="mt-2 flex gap-2">
            <Button size="sm" variant="primary" disabled={!allChecked}
              onClick={() => act('release_recommend', { checklist: checks, remarks: note || undefined }, t('Recommended for release'))}>{t('Recommend release')}</Button>
            <Button size="sm" variant="ghost" onClick={() => act('release_decide', { approve: false, remarks: note || t('Conditions not met.') }, t('Release declined'))}>{t('Decline')}</Button>
          </div>
        </div>
      )}
      {r?.status === 'RECOMMENDED' && p.approve_release && (
        <div className="flex flex-wrap gap-2 border-t border-slate-100 px-4 py-3">
          <Textarea rows={2} placeholder={t('Order / remarks')} value={note} onChange={(e) => setNote(e.target.value)} />
          <Button size="sm" variant="success" onClick={() => act('release_decide', { approve: true, remarks: note || undefined }, t('Release approved'))}>{t('Approve release')}</Button>
          <Button size="sm" variant="ghost" onClick={() => act('release_decide', { approve: false, remarks: note || t('Not approved.') }, t('Release not approved'))}>{t('Do not approve')}</Button>
        </div>
      )}
      {r?.status === 'APPROVED' && p.execute_release && (
        <div className="border-t border-slate-100 px-4 py-3">
          <Button size="sm" variant="primary" icon={<Stamp className="size-4" />} onClick={() => act('release_execute', {}, t('Lien released; letter issued to the bank'))}>
            {t('Release lien and issue letter to bank')}
          </Button>
        </div>
      )}
      {p.request_release && !(r && ['REQUESTED', 'RECOMMENDED', 'APPROVED'].includes(r.status)) && (
        <div className="border-t border-slate-100 px-4 py-3">
          <Button size="sm" onClick={() => setAsking(true)}>{t('Request release or refund')}</Button>
        </div>
      )}
      <Modal open={asking} onClose={() => setAsking(false)} title={t('Request release or refund')}
        footer={<Button variant="primary" disabled={!reason} onClick={async () => { await act('release_request', { reason, remarks: details || undefined }, t('Release requested')); setAsking(false) }}>{t('Send request')}</Button>}>
        <div className="space-y-3">
          <Field label={t('Reason')}>
            <Select value={reason} onChange={(e) => setReason(e.target.value)}>
              <option value="" />
              {meta.data?.release_reasons.map((r) => <option key={r.value} value={r.value}>{t(r.label)}</option>)}
            </Select>
          </Field>
          <Field label={t('Details')}>
            <Textarea rows={3} value={details} onChange={(e) => setDetails(e.target.value)} />
          </Field>
        </div>
      </Modal>
    </Card>
  )
}

function Rectify({ x, act, upload }: { x: Detail; act: Act; upload: (f: File) => Promise<void> }) {
  const editable = ['fdr_number', 'amount', 'issue_date', 'maturity_date', 'depositor_name', 'lien_holder']
  const [vals, setVals] = useState<Record<string, string>>(() =>
    Object.fromEntries(x.compare.filter((r) => editable.includes(r.field)).map((r) => [r.field, r.declared == null ? '' : String(r.declared)])))
  const [note, setNote] = useState('')
  const file = useRef<HTMLInputElement>(null)
  return (
    <Card className="border-seal-100">
      <CardHeader icon={<CircleAlert className="size-4.5 text-seal-600" />} title={t('Rectify and resubmit')}
        subtitle={t('Correct the particulars and upload the corrected or fresh FDR copy. The checks run again as soon as you resubmit.')} />
      <div className="grid gap-3 px-4 py-3 sm:grid-cols-3">
        {x.compare.filter((r) => editable.includes(r.field)).map((r) => (
          <Field key={r.field} label={t(r.label)}>
            <Input value={vals[r.field]} type={r.field.endsWith('_date') ? 'date' : 'text'} onChange={(e) => setVals({ ...vals, [r.field]: e.target.value })} />
          </Field>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 px-4 py-3">
        <input ref={file} type="file" accept=".pdf,.png,.jpg,.jpeg" className="hidden" onChange={async (e) => { const f = e.target.files?.[0]; if (f) await upload(f); e.target.value = '' }} />
        <Button size="sm" icon={<FileUp className="size-4" />} onClick={() => file.current?.click()}>{t('Upload corrected FDR copy')}</Button>
        <Input className="max-w-sm" placeholder={t('Remarks')} value={note} onChange={(e) => setNote(e.target.value)} />
        <Button size="sm" variant="primary" onClick={() => act('rectify', { corrections: vals, remarks: note || undefined }, t('Resubmitted'))}>{t('Resubmit')}</Button>
      </div>
    </Card>
  )
}

function Papers({ x }: { x: Detail }) {
  const letters = useQuery({ queryKey: ['instrument', x.id, 'letters'], queryFn: () => api.get<LetterOut[]>(`/instruments/${x.id}/letters`) })
  const dl = (path: string, name: string) => download(path, undefined, name).catch((e) => toast.error(errorMessage(e)))
  return (
    <Card>
      <CardHeader icon={<FileDown className="size-4.5" />} title={t('Documents and letters')} subtitle={t('Each file is stored with its SHA-256 fingerprint.')} />
      <ul className="divide-y divide-slate-100">
        {x.documents.map((d) => (
          <li key={d.id} className="flex items-center gap-3 px-4 py-2 text-[14px]">
            <span className="min-w-0 flex-1">
              <button onClick={() => dl(`/documents/${d.id}`, d.filename)} className="block truncate text-left text-brand-800 hover:underline">{d.filename}</button>
              <span className="text-[12.5px] text-slate-500">{d.doc_type.replace('_', ' ').toLowerCase()} · {fileSize(d.size_bytes)} · {fmtDate(d.uploaded_at)} · <span className="tabular">{d.sha256.slice(0, 12)}…</span></span>
            </span>
          </li>
        ))}
        {letters.data?.map((l) => (
          <li key={l.id} className="flex items-center gap-3 px-4 py-2 text-[14px]">
            <QrCode className="size-4 shrink-0 text-ink-green-600" />
            <span className="min-w-0 flex-1">
              <button onClick={() => dl(`/letters/${l.code}/pdf`, `${l.code}.pdf`)} className="block truncate text-left text-brand-800 hover:underline">{LETTER_KIND[l.kind] ?? l.kind}</button>
              <span className="text-[12.5px] text-slate-500">{t('to')} {l.addressee} · {fmtDate(l.issued_at)}</span>
            </span>
            <Link to={`/verify/${l.code}`} className="file-no text-[12px]">{l.code}</Link>
          </li>
        ))}
        {!x.documents.length && !letters.data?.length && <li className="px-4 py-3 text-[14px] text-slate-500">{t('No documents yet.')}</li>}
      </ul>
    </Card>
  )
}

function History({ x }: { x: Detail }) {
  const chain = useQuery({ queryKey: ['instrument', x.id, 'chain'], queryFn: () => api.get<{ valid: boolean; events: number; broken_at_seq: number | null }>(`/instruments/${x.id}/verify`) })
  return (
    <Card>
      <CardHeader
        title={t('History')}
        subtitle={t('Every step, sealed in a hash chain. Editing any entry outside the portal breaks the chain.')}
        actions={chain.data && (chain.data.valid
          ? <Badge className="bg-ink-green-50 text-ink-green-700 ring-ink-green-100"><ShieldCheck className="size-3.5" /> {t('Chain intact')}</Badge>
          : <Badge className="bg-seal-600 text-white ring-seal-600">{t('Broken at entry {n}', { n: chain.data.broken_at_seq ?? '?' })}</Badge>)}
      />
      <ol className="px-4 py-2">
        {[...x.events].reverse().map((e) => (
          <li key={e.id} className="relative border-l border-slate-200 py-2 pl-4">
            <span className="absolute top-3.5 -left-[4.5px] size-2 rounded-full bg-brand-700" />
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-[14.5px] font-semibold text-brand-900">{t(e.label)}</span>
              <span className="text-[13px] text-slate-500">{e.actor_label}</span>
              <span className="tabular text-[12.5px] text-slate-400">{fmtDateTime(e.occurred_at)}</span>
            </div>
            {e.remarks && <p className="text-[14px] text-slate-700">{e.remarks}</p>}
            <p className="tabular text-[11.5px] text-slate-400" title={e.hash}>#{e.seq} · {e.hash.slice(0, 16)}</p>
          </li>
        ))}
      </ol>
    </Card>
  )
}

export default function InstrumentDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['instrument', Number(id)], queryFn: () => api.get<Detail>(`/instruments/${id}`) })
  const meta = useMeta()
  const [assignTo, setAssignTo] = useState('')
  const [rejecting, setRejecting] = useState(false)
  const [rejectNote, setRejectNote] = useState('')
  const mutate = useMutation({
    mutationFn: ({ action, body }: { action: string; body: Record<string, unknown> }) => api.post<Detail>(`/instruments/${id}/actions/${action}`, body),
  })
  const act: Act = async (action, body = {}, ok) => {
    try {
      const fresh = await mutate.mutateAsync({ action, body })
      qc.setQueryData(['instrument', Number(id)], fresh)
      qc.invalidateQueries({ queryKey: ['instrument', Number(id)] })
      qc.invalidateQueries({ queryKey: ['instruments'] })
      qc.invalidateQueries({ queryKey: ['my-work'] })
      if (ok) toast.success(ok)
    } catch (e) {
      toast.error(errorMessage(e))
      throw e instanceof ApiError ? e : new Error(errorMessage(e))
    }
  }
  const upload = async (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('doc_type', 'FDR_COPY')
    try {
      const res = await fetch(`/api/instruments/${id}/documents`, { method: 'POST', body: fd, headers: { Authorization: `Bearer ${getToken()}` } })
      if (!res.ok) throw new Error((await res.json()).detail ?? 'Upload failed')
      qc.setQueryData(['instrument', Number(id)], await res.json())
      qc.invalidateQueries({ queryKey: ['instrument', Number(id), 'letters'] })
      toast.success(t('Document attached and read'))
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }
  if (q.isLoading) return <Loading />
  if (q.error) return <ErrorState error={q.error} retry={q.refetch} />
  const x = q.data!
  const p = x.permissions
  const pending = ['SUBMITTED', 'UNDER_SCRUTINY', 'DISCREPANCY'].includes(x.status)
  const safeAct = (a: string, b?: Record<string, unknown>, ok?: string) => act(a, b, ok).catch(() => undefined)
  return (
    <div>
      <Link to="/instruments" className="mb-3 inline-flex items-center gap-1 text-[14px] text-slate-500 hover:text-brand-800">
        <ArrowLeft className="size-4" /> {t('Deposits')}
      </Link>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <RefNo>{x.ref_no}</RefNo>
            <StatusBadge status={x.status} />
            <MaturityBadge days={x.days_to_maturity} status={x.status} />
            {x.escalation_level > 0 && <Badge className="bg-seal-50 text-seal-700 ring-seal-100">{x.escalation_level === 2 ? t('Escalated to competent authority') : t('Escalated to RB head')}</Badge>}
          </div>
          <h1 className="mt-2 text-[28px] leading-tight font-semibold text-brand-900" style={{ fontStretch: '88%' }}>
            <span className="figure">{fmtINR(x.amount)}</span>
            <span className="text-slate-400"> · </span>
            {x.kind === 'FDR' ? t('FDR {n}', { n: x.fdr_number }) : t('Deposit {n}', { n: x.fdr_number })}
          </h1>
          <p className="mt-1 text-[15px] text-slate-600">
            {user?.role !== 'INSTITUTION'
              ? <Link to={`/institutions/${x.institution.id}`} className="text-brand-800 hover:underline">{x.institution.name}, {x.institution.city}</Link>
              : <>{x.institution.name}, {x.institution.city}</>}
            {' · '}{PURPOSE[x.purpose]} {x.approval_year}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {p.scrutinise && x.status === 'SUBMITTED' && <Button size="sm" onClick={() => safeAct('start_scrutiny', {}, t('Scrutiny started'))}>{t('Start scrutiny')}</Button>}
          {p.scrutinise && pending && x.open_discrepancies > 0 && x.status !== 'DISCREPANCY' && (
            <Button size="sm" variant="warning" onClick={() => safeAct('send_for_rectification', {}, t('Sent to the institution with a rectification letter'))}>{t('Send for rectification')}</Button>
          )}
          {p.scrutinise && pending && (
            <Button size="sm" variant="success" icon={<Check className="size-4" />}
              disabled={x.open_discrepancies > 0 || (x.kind === 'FDR' && x.verification_status !== 'CONFIRMED')}
              title={x.open_discrepancies > 0 ? t('Resolve or waive the open discrepancies first') : x.verification_status !== 'CONFIRMED' ? t('The bank has not confirmed this FDR yet') : undefined}
              onClick={() => safeAct('accept', {}, t('Accepted as security'))}>{t('Accept as security')}</Button>
          )}
          {p.scrutinise && pending && <Button size="sm" variant="ghost" onClick={() => setRejecting(true)}>{t('Reject')}</Button>}
          {p.renew && <ButtonLink size="sm" to={`/instruments/new?replaces=${x.id}`} icon={<RefreshCcw className="size-4" />}>{t('Lodge renewal')}</ButtonLink>}
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.6fr_1fr]">
        <div className="min-w-0 space-y-5">
          {x.status === 'DISCREPANCY' && p.rectify && <Rectify x={x} act={safeAct} upload={upload} />}
          <ThreeSources x={x} />
          <Discrepancies x={x} act={safeAct} />
          <ReleasePanel x={x} act={safeAct} />
          <History x={x} />
        </div>
        <div className="min-w-0 space-y-5">
          <Card>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-4">
              <KeyValue label={t('Issued')}>{fmtDate(x.issue_date)}</KeyValue>
              <KeyValue label={t('Matures')}>{fmtDate(x.maturity_date)}</KeyValue>
              <KeyValue label={t('Required amount')}>{x.required_amount ? fmtLakh(x.required_amount) : '—'}</KeyValue>
              <KeyValue label={t('Required valid until')}>{fmtDate(x.required_valid_until)}</KeyValue>
              <KeyValue label={t('Depositor')} className="col-span-2">{x.depositor_name}</KeyValue>
              <KeyValue label={t('Lien in favour of')} className="col-span-2">{x.lien_holder || <span className="text-seal-600">{t('No lien marked')}</span>}</KeyValue>
              <KeyValue label={t('Auto-renewal with bank')}>{x.auto_renewal ? t('Yes') : t('No')}</KeyValue>
              <KeyValue label={t('Dealing officer')}>{x.assigned_officer?.full_name ?? '—'}</KeyValue>
              {x.replaces && (
                <KeyValue label={t('Renews')} className="col-span-2">
                  <Link to={`/instruments/${x.replaces.id}`} className="file-no">{x.replaces.ref_no}</Link> <span className="text-[13px] text-slate-500">{t('matured')} {fmtDate(x.replaces.maturity_date)}</span>
                </KeyValue>
              )}
              {x.renewed_late !== null && x.status === 'RENEWED' && (
                <KeyValue label={t('Renewal')} className="col-span-2">{x.renewed_late ? <span className="text-seal-700">{t('Lodged after maturity')}</span> : <span className="text-ink-green-700">{t('Lodged before maturity')}</span>}</KeyValue>
              )}
            </dl>
            {p.assign && pending && (
              <div className="flex gap-2 border-t border-slate-100 px-4 py-3">
                <Select value={assignTo} onChange={(e) => setAssignTo(e.target.value)} aria-label={t('Assign to')}>
                  <option value="">{t('Assign to an officer…')}</option>
                  {meta.data?.officers.filter((o) => o.role === 'RB_OFFICER').map((o) => <option key={o.id} value={o.id}>{o.full_name}</option>)}
                </Select>
                <Button size="sm" disabled={!assignTo} onClick={() => safeAct('assign', { officer_id: Number(assignTo) }, t('Assigned'))}>{t('Assign')}</Button>
              </div>
            )}
          </Card>
          {x.renewal_risk !== null && ['ACTIVE', 'EXPIRING'].includes(x.status) && user?.role !== 'INSTITUTION' && (
            <Card className="px-4 py-4"><RenewalRiskPanel risk={x.renewal_risk} drivers={x.renewal_drivers} /></Card>
          )}
          <BankPanel x={x} act={safeAct} />
          <Papers x={x} />
        </div>
      </div>
      <Modal open={rejecting} onClose={() => setRejecting(false)} title={t('Reject this instrument')}
        footer={<Button variant="danger" disabled={rejectNote.trim().length < 10} onClick={async () => { await safeAct('reject', { remarks: rejectNote }, t('Rejected')); setRejecting(false) }}>{t('Reject')}</Button>}>
        <Field label={t('Reason')} hint={t('Sent to the institution and kept in the sealed history.')}>
          <Textarea rows={3} value={rejectNote} onChange={(e) => setRejectNote(e.target.value)} />
        </Field>
      </Modal>
    </div>
  )
}
