import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { FileUp, ScanText } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Button, Card, CardHeader, Field, Input, NotForRole, PageHeader, RefNo, Select, Toggle } from '@/components/ui'
import { api, errorMessage, getToken } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDate, fmtINR, fmtLakh } from '@/lib/format'
import { useDebounced, useMeta } from '@/lib/hooks'
import { t } from '@/lib/i18n'
import type { Institution, InstrumentDetail, Page } from '@/lib/types'

interface Read {
  token: string
  filename: string
  values: Record<string, string | number>
  confidence: number
  sha256: string
}

const FIELDS = ['fdr_number', 'amount', 'issue_date', 'maturity_date', 'depositor_name', 'lien_holder'] as const

function yearNow() {
  const d = new Date()
  const y = d.getMonth() >= 3 ? d.getFullYear() : d.getFullYear() - 1
  return `${y}-${String((y + 1) % 100).padStart(2, '0')}`
}

function addMonths(iso: string, months: number) {
  const d = new Date(iso + 'T00:00:00')
  d.setMonth(d.getMonth() + months)
  return d.toISOString().slice(0, 10)
}

export default function NewInstrument() {
  const { user, canLodge, isInstitution } = useAuth()
  const meta = useMeta()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const replacesId = params.get('replaces')
  const [inst, setInst] = useState<Institution | null>(null)
  const [instQ, setInstQ] = useState('')
  const dq = useDebounced(instQ, 250)
  const [read, setRead] = useState<Read | null>(null)
  const [reading, setReading] = useState(false)
  const [busy, setBusy] = useState(false)
  const file = useRef<HTMLInputElement>(null)
  const [f, setF] = useState({
    purpose: 'NEW_PROGRAMME', approval_year: yearNow(), application_ref: '', bank_id: '', branch: '', ifsc: '',
    fdr_number: '', depositor_name: '', amount: '', issue_date: '', maturity_date: '', lien_holder: '', auto_renewal: false,
  })
  const set = (patch: Partial<typeof f>) => setF((v) => ({ ...v, ...patch }))

  const replaces = useQuery({
    queryKey: ['instrument', Number(replacesId)],
    queryFn: () => api.get<InstrumentDetail>(`/instruments/${replacesId}`),
    enabled: !!replacesId,
  })
  const own = useQuery({
    queryKey: ['institution', user?.institution?.id],
    queryFn: () => api.get<Institution>(`/institutions/${user!.institution!.id}`),
    enabled: isInstitution && !!user?.institution,
  })
  const search = useQuery({
    queryKey: ['inst-search', dq],
    queryFn: () => api.get<Page<Institution>>('/institutions', { q: dq, page_size: 8, with_deposits: false, sort: 'name' }),
    enabled: !isInstitution && dq.length >= 2 && !inst,
  })
  useEffect(() => {
    if (own.data) setInst(own.data)
  }, [own.data])
  useEffect(() => {
    const r = replaces.data
    if (!r) return
    setInst(r.institution as Institution)
    set({ purpose: r.purpose, bank_id: r.bank ? String(r.bank.id) : '', branch: r.branch ?? '', ifsc: r.ifsc ?? '',
          depositor_name: r.depositor_name, amount: String(r.required_amount ?? r.amount), lien_holder: r.lien_holder ?? '' })
  }, [replaces.data])
  useEffect(() => {
    if (meta.data && !f.lien_holder) set({ lien_holder: meta.data.lien_holder })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta.data])
  useEffect(() => {
    if (inst?.society_name && !f.depositor_name) set({ depositor_name: inst.society_name })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inst])

  const rule = useMemo(() => {
    const rules = meta.data?.deposit_rules ?? []
    return rules.find((r) => r.purpose === f.purpose && r.inst_type === inst?.inst_type) ?? rules.find((r) => r.purpose === f.purpose && r.inst_type === '*')
  }, [meta.data, f.purpose, inst])
  const amount = Number(f.amount)
  const shortAmount = rule && amount > 0 && amount < rule.amount
  const shortTenure = rule && f.issue_date && f.maturity_date && f.maturity_date < addMonths(f.issue_date, rule.min_tenure_months)

  if (!canLodge) return <NotForRole title={t('Lodge an FDR')}>{t('Only institutions and Regulation Bureau officers lodge deposits.')}</NotForRole>

  const readFile = async (file: File) => {
    setReading(true)
    const fd = new FormData()
    fd.append('file', file)
    try {
      const res = await fetch('/api/instruments/read-document', { method: 'POST', body: fd, headers: { Authorization: `Bearer ${getToken()}` } })
      const body = await res.json()
      if (!res.ok) throw new Error(body.detail ?? 'Could not read the file')
      setRead(body)
      const v = body.values as Record<string, string | number>
      set({
        fdr_number: String(v.fdr_number ?? f.fdr_number), amount: v.amount ? String(v.amount) : f.amount,
        issue_date: String(v.issue_date ?? f.issue_date), maturity_date: String(v.maturity_date ?? f.maturity_date),
        depositor_name: String(v.depositor_name ?? f.depositor_name), lien_holder: String(v.lien_holder ?? f.lien_holder),
        ifsc: String(v.ifsc ?? f.ifsc), branch: String(v.branch ?? f.branch),
      })
      if (v.bank_name && meta.data) {
        const b = meta.data.banks.find((b) => String(v.bank_name).toLowerCase().includes(b.name.toLowerCase()))
        if (b) set({ bank_id: String(b.id) })
      }
      if (v.ifsc && meta.data) {
        const b = meta.data.banks.find((b) => String(v.ifsc).toUpperCase().startsWith(b.code))
        if (b) set({ bank_id: String(b.id) })
      }
      toast.success(t('Read {n}% of the fields from the document. Check them before submitting.', { n: Math.round(body.confidence * 100) }))
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setReading(false)
    }
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!inst) return toast.error(t('Choose the institution'))
    setBusy(true)
    try {
      const x = await api.post<InstrumentDetail>('/instruments', {
        institution_id: inst.id, purpose: f.purpose, approval_year: f.approval_year, application_ref: f.application_ref || undefined,
        bank_id: f.bank_id ? Number(f.bank_id) : undefined, branch: f.branch || undefined, ifsc: f.ifsc || undefined,
        fdr_number: f.fdr_number, depositor_name: f.depositor_name, amount: Number(f.amount), issue_date: f.issue_date,
        maturity_date: f.maturity_date, lien_holder: f.lien_holder || undefined, auto_renewal: f.auto_renewal,
        replaces_id: replacesId ? Number(replacesId) : undefined, document_token: read?.token,
      })
      toast.success(t('Lodged as {ref}. Acknowledgement issued.', { ref: x.ref_no }))
      navigate(`/instruments/${x.id}`)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const docVal = (k: string) => read?.values[k]
  const differs = (k: (typeof FIELDS)[number]) => {
    const d = docVal(k)
    if (d === undefined || d === null) return false
    const mine = (f as Record<string, unknown>)[k]
    return k === 'amount' ? Number(d) !== Number(mine) : String(d).trim().toLowerCase() !== String(mine).trim().toLowerCase()
  }
  const docHint = (k: (typeof FIELDS)[number]) => {
    const d = docVal(k)
    if (d === undefined) return undefined
    const shown = k === 'amount' ? fmtINR(Number(d)) : k.endsWith('_date') ? fmtDate(String(d)) : String(d)
    return differs(k) ? <span className="text-seal-600">{t('The FDR copy says')} {shown}</span> : <span className="text-ink-green-700">{t('Matches the FDR copy')}</span>
  }

  return (
    <div className="max-w-5xl">
      <PageHeader
        title={replacesId ? t('Lodge a renewal') : isInstitution ? t('Lodge an FDR') : t('Lodge an FDR on behalf of an institution')}
        subtitle={t('Upload the FDR copy first: the portal reads it and fills in the particulars. What you declare and what the document says are both kept, and the bank is asked to confirm.')}
      />
      {replaces.data && (
        <p className="mb-4 text-[15px] text-slate-700">
          {t('Replaces')} <RefNo>{replaces.data.ref_no}</RefNo> · {replaces.data.bank?.short_name} {replaces.data.fdr_number} · {t('matures')} {fmtDate(replaces.data.maturity_date)}
        </p>
      )}
      <form onSubmit={submit} className="grid gap-5 lg:grid-cols-[1fr_320px]">
        <div className="space-y-5">
          {!isInstitution && !replacesId && (
            <Card>
              <CardHeader title={t('Institution')} />
              <div className="px-4 py-3">
                {inst ? (
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-[15px] font-semibold text-brand-900">{inst.name}, {inst.city}</div>
                      <div className="text-[13px] text-slate-500">{inst.aicte_pid} · {inst.inst_type} · {inst.society_name}</div>
                    </div>
                    <Button size="sm" variant="ghost" onClick={() => { setInst(null); setInstQ('') }}>{t('Change')}</Button>
                  </div>
                ) : (
                  <>
                    <Input value={instQ} onChange={(e) => setInstQ(e.target.value)} placeholder={t('Name, city or AICTE Permanent ID')} aria-label={t('Find institution')} />
                    <ul className="mt-2">
                      {search.data?.items.map((i) => (
                        <li key={i.id}>
                          <button type="button" onClick={() => setInst(i)} className="w-full rounded px-2 py-1.5 text-left hover:bg-slate-50">
                            <span className="text-[15px] text-brand-900">{i.name}, {i.city}</span>
                            <span className="ml-2 text-[13px] text-slate-500">{i.aicte_pid}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            </Card>
          )}
          <Card>
            <CardHeader icon={<ScanText className="size-4.5" />} title={t('FDR copy')} subtitle={t('The PDF from the bank, or a scan or phone photo of the receipt (PNG or JPG). Up to 10 MB. Scans and photos are read by OCR.')} />
            <div className="px-4 py-4">
              <input ref={file} type="file" accept=".pdf,.png,.jpg,.jpeg" className="hidden" onChange={(e) => { const x = e.target.files?.[0]; if (x) readFile(x); e.target.value = '' }} />
              <button
                type="button"
                onClick={() => file.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { e.preventDefault(); const x = e.dataTransfer.files?.[0]; if (x) readFile(x) }}
                className={clsx('flex w-full flex-col items-center gap-1 rounded-[6px] border-2 border-dashed px-4 py-6 text-center', read ? 'border-ink-green-100 bg-ink-green-50/40' : 'border-slate-300 hover:border-brand-400')}
              >
                <FileUp className="size-6 text-slate-400" />
                {reading ? <span className="text-[15px] text-slate-600">{t('Reading the document…')}</span>
                  : read ? <>
                    <span className="text-[15px] font-semibold text-brand-900">{read.filename}</span>
                    <span className="text-[13px] text-slate-500">{t('{n}% of the fields read', { n: Math.round(read.confidence * 100) })} · SHA-256 <span className="tabular">{read.sha256.slice(0, 12)}…</span> · {t('click to replace')}</span>
                  </> : <>
                    <span className="text-[15px] font-semibold text-brand-900">{t('Drop the FDR copy here, or choose a file')}</span>
                    <span className="text-[13px] text-slate-500">{t('Read on this server. Nothing is sent outside.')}</span>
                  </>}
              </button>
            </div>
          </Card>
          <Card>
            <CardHeader title={t('Particulars, as declared')} subtitle={t('Check each one against the paper. Differences from the FDR copy are shown under the field.')} />
            <div className="grid gap-4 px-4 py-4 sm:grid-cols-2">
              <Field label={t('Purpose')} required>
                <Select value={f.purpose} onChange={(e) => set({ purpose: e.target.value })}>
                  {meta.data?.purposes.map((p) => <option key={p.value} value={p.value}>{t(p.label)}</option>)}
                </Select>
              </Field>
              <Field label={t('Approval year')} required>
                <Input value={f.approval_year} onChange={(e) => set({ approval_year: e.target.value })} pattern="\d{4}-\d{2}" />
              </Field>
              <Field label={t('Bank')} required>
                <Select value={f.bank_id} onChange={(e) => set({ bank_id: e.target.value })} required>
                  <option value="" />
                  {meta.data?.banks.map((b) => <option key={b.id} value={b.id}>{b.name}{b.is_scheduled ? '' : ` (${t('not scheduled')})`}</option>)}
                </Select>
              </Field>
              <Field label={t('Branch')}>
                <Input value={f.branch} onChange={(e) => set({ branch: e.target.value })} />
              </Field>
              <Field label="IFSC">
                <Input value={f.ifsc} onChange={(e) => set({ ifsc: e.target.value.toUpperCase() })} maxLength={11} />
              </Field>
              <Field label={t('FDR number')} required hint={docHint('fdr_number')}>
                <Input value={f.fdr_number} onChange={(e) => set({ fdr_number: e.target.value })} required />
              </Field>
              <Field label={t('Amount (₹)')} required hint={docHint('amount') ?? (amount > 0 ? fmtINR(amount) : undefined)}
                error={shortAmount ? t('Below the {n} required for this purpose', { n: fmtLakh(rule!.amount) }) : undefined}>
                <Input value={f.amount} onChange={(e) => set({ amount: e.target.value.replace(/[^\d.]/g, '') })} inputMode="decimal" required />
              </Field>
              <Field label={t('Depositor (as on the FDR)')} required hint={docHint('depositor_name')}>
                <Input value={f.depositor_name} onChange={(e) => set({ depositor_name: e.target.value })} required />
              </Field>
              <Field label={t('Issue date')} required hint={docHint('issue_date')}>
                <Input type="date" value={f.issue_date} onChange={(e) => set({ issue_date: e.target.value })} required />
              </Field>
              <Field label={t('Maturity date')} required hint={docHint('maturity_date')}
                error={shortTenure ? t('Shorter than the {n} months required', { n: rule!.min_tenure_months }) : undefined}>
                <Input type="date" value={f.maturity_date} onChange={(e) => set({ maturity_date: e.target.value })} required />
              </Field>
              <Field label={t('Lien marked in favour of')} hint={docHint('lien_holder')} className="sm:col-span-2">
                <Input value={f.lien_holder} onChange={(e) => set({ lien_holder: e.target.value })} />
              </Field>
              <Field label={t('AICTE application number')}>
                <Input value={f.application_ref} onChange={(e) => set({ application_ref: e.target.value })} />
              </Field>
              <div className="flex items-end pb-1.5">
                <Toggle checked={f.auto_renewal} onChange={(v) => set({ auto_renewal: v })} label={t('Auto-renewal instruction given to the bank')} />
              </div>
            </div>
          </Card>
        </div>
        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <Card className="px-4 py-4">
            <h3 className="text-[16px] font-semibold text-brand-900">{t('What is required')}</h3>
            {rule ? (
              <dl className="mt-2 space-y-2 text-[14px]">
                <div><dt className="text-slate-500">{t('Amount')}</dt><dd className="figure text-[20px] text-brand-900">{fmtLakh(rule.amount)}</dd></div>
                <div><dt className="text-slate-500">{t('Valid for at least')}</dt><dd className="figure text-[20px] text-brand-900">{rule.min_tenure_months} {t('months')}</dd></div>
                <div><dt className="text-slate-500">{t('Lien')}</dt><dd>{meta.data?.lien_holder}</dd></div>
              </dl>
            ) : <p className="mt-2 text-[14px] text-slate-500">{t('Choose the institution and purpose.')}</p>}
            <p className="mt-3 text-[12.5px] text-slate-500">{t('Demonstration norms, set by the administrator; not AICTE’s published figures.')}</p>
          </Card>
          <Button type="submit" variant="primary" className="w-full" loading={busy} disabled={!inst}>{t('Lodge')}</Button>
          <p className="text-[13px] text-slate-500">{t('You will get an acknowledgement letter with a QR code at once. The checks run as soon as it is lodged.')}</p>
        </aside>
      </form>
    </div>
  )
}
