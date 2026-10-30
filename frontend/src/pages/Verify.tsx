import { useMutation, useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { FileCheck2, QrCode, ShieldAlert, ShieldCheck } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Button, Input, Loading } from '@/components/ui'
import { ApiError } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDate, fmtINR } from '@/lib/format'
import { t } from '@/lib/i18n'

interface Result {
  code: string
  kind: string
  kind_label: string
  subject: string
  issued_on: string
  addressee: string
  valid: boolean
  sha256: string
  instrument: { ref_no: string; institution: string; bank: string; fdr_last4: string; amount: number; maturity_date: string }
}

async function get<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init)
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(res.status, body.detail ?? `Request failed (${res.status})`)
  return body as T
}

/** Public: anyone holding a letter from the portal can confirm AICTE issued it and that the PDF is unaltered. */
export default function Verify() {
  const { code } = useParams()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [input, setInput] = useState(code ?? '')
  const q = useQuery({ queryKey: ['public-verify', code], queryFn: () => get<Result>(`/public/verify/${encodeURIComponent(code!)}`), enabled: !!code, retry: false })
  const file = useMutation({
    mutationFn: (f: File) => {
      const fd = new FormData()
      fd.append('file', f)
      return get<{ matches: boolean; uploaded_sha256: string; issued_sha256: string }>(`/public/verify/${encodeURIComponent(code!)}/file`, { method: 'POST', body: fd })
    },
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (input.trim()) navigate(`/verify/${input.trim().toUpperCase()}`)
  }
  const r = q.data
  const body = (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6 flex items-center gap-3">
        <QrCode className="size-8 text-brand-800" />
        <div>
          <h1 className="text-[28px] leading-tight font-semibold text-brand-900">{t('Verify a letter')}</h1>
          <p className="text-[15px] text-slate-600">{t('Every letter the portal issues carries a code and a QR. Enter the code to confirm AICTE issued it.')}</p>
        </div>
      </div>
      <form onSubmit={submit} className="flex gap-2">
        <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder="NDL-XXXXXXXX" aria-label={t('Letter code')} className="figure text-[17px] uppercase" />
        <Button type="submit" variant="primary">{t('Verify')}</Button>
      </form>
      {q.isLoading && <Loading />}
      {q.error && (
        <div className="mt-6 flex gap-3 rounded-[6px] border border-seal-100 bg-seal-50 p-4">
          <ShieldAlert className="size-7 shrink-0 text-seal-600" />
          <div>
            <div className="text-[18px] font-semibold text-seal-700">{t('Not issued by the portal')}</div>
            <p className="text-[15px] text-slate-700">{(q.error as Error).message}</p>
          </div>
        </div>
      )}
      {r && (
        <div className="mt-6 space-y-4">
          <div className={clsx('flex gap-3 rounded-[6px] border p-4', r.valid ? 'border-ink-green-100 bg-ink-green-50' : 'border-seal-100 bg-seal-50')}>
            {r.valid ? <ShieldCheck className="size-7 shrink-0 text-ink-green-600" /> : <ShieldAlert className="size-7 shrink-0 text-seal-600" />}
            <div>
              <div className={clsx('text-[19px] font-semibold', r.valid ? 'text-ink-green-700' : 'text-seal-700')}>
                {r.valid ? t('Genuine. Issued by the AICTE deposit portal.') : t('This letter has been withdrawn.')}
              </div>
              <p className="text-[15px] text-slate-700">{t(r.kind_label)} · {t('issued')} {fmtDate(r.issued_on)} · {t('to')} {r.addressee}</p>
            </div>
          </div>
          <dl className="sheet grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-4 text-[15px]">
            <div className="col-span-2"><dt className="text-[13px] text-slate-500">{t('Subject')}</dt><dd>{r.subject}</dd></div>
            <div><dt className="text-[13px] text-slate-500">{t('Institution')}</dt><dd>{r.instrument.institution}</dd></div>
            <div><dt className="text-[13px] text-slate-500">{t('Bank')}</dt><dd>{r.instrument.bank}</dd></div>
            <div><dt className="text-[13px] text-slate-500">{t('FDR')}</dt><dd className="figure">{r.instrument.fdr_last4}</dd></div>
            <div><dt className="text-[13px] text-slate-500">{t('Amount')}</dt><dd className="figure">{fmtINR(r.instrument.amount)}</dd></div>
            <div><dt className="text-[13px] text-slate-500">{t('Reference')}</dt><dd className="file-no w-fit">{r.instrument.ref_no}</dd></div>
            <div><dt className="text-[13px] text-slate-500">{t('Matures')}</dt><dd>{fmtDate(r.instrument.maturity_date)}</dd></div>
          </dl>
          <div className="sheet px-4 py-4">
            <div className="flex items-center gap-2 text-[15px] font-semibold text-brand-900"><FileCheck2 className="size-4.5" /> {t('Check your copy of the PDF')}</div>
            <p className="mt-1 text-[14px] text-slate-600">{t('Choose the PDF you received. It is compared byte for byte with the one the portal issued; even one changed character shows.')}</p>
            <input type="file" accept=".pdf" className="mt-3 text-[14px]" onChange={(e) => { const f = e.target.files?.[0]; if (f) file.mutate(f) }} />
            {file.data && (
              <p className={clsx('mt-3 text-[15px] font-semibold', file.data.matches ? 'text-ink-green-700' : 'text-seal-700')}>
                {file.data.matches ? t('Identical to the letter issued.') : t('This file is NOT the letter issued: it has been altered.')}
              </p>
            )}
            <p className="mt-2 break-all text-[12px] text-slate-500">SHA-256 {r.sha256}</p>
          </div>
        </div>
      )}
    </div>
  )
  if (user) return body
  return (
    <div className="min-h-screen bg-canvas px-4 py-10">
      {body}
      <p className="mt-10 text-center text-[14px] text-slate-500"><Link to="/login" className="text-brand-700 hover:underline">{t('Sign in to the portal')}</Link></p>
    </div>
  )
}
