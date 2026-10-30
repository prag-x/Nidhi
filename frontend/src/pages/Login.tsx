import { useQuery } from '@tanstack/react-query'
import { ArrowRight } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Button, Field, Input } from '@/components/ui'
import { api, errorMessage } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { ROLE } from '@/lib/labels'
import type { Role } from '@/lib/types'
import { isHindi, setLang, t } from '@/lib/i18n'

interface DemoAccounts {
  password: string
  accounts: { email: string; full_name: string; designation: string; role: Role; unit: string | null; hint?: string }[]
}

const POINTS = [
  [t('Three sources, never mixed'), t('What the institution declared, what its FDR copy says, and what the bank confirmed sit side by side for every field.')],
  [t('Nothing matures unnoticed'), t('Reminders at 90, 60, 30 and 7 days, then escalation to the RB head and the competent authority.')],
  [t('Release only by maker-checker'), t('Conditions checked, recommended by the Bureau, approved by the competent authority, executed by Accounts.')],
  [t('Letters anyone can verify'), t('Every acknowledgement and lien-release letter carries a QR code and a fingerprint of the PDF.')],
]

function Specimen() {
  const rows = [
    [t('Amount'), '₹15,00,000', '₹1,50,000', '₹15,00,000'],
    [t('Matures'), '12 Nov 2031', '12 Nov 2031', '12 Nov 2031'],
    [t('Lien'), 'MS, AICTE', 'MS, AICTE', 'MS, AICTE'],
  ]
  return (
    <div className="sheet mt-8 overflow-hidden text-[14px]" aria-hidden>
      <div className="grid grid-cols-[1fr_1.2fr_1.2fr_1.2fr] border-b border-slate-200 bg-slate-50 px-4 py-2 text-[12.5px] text-slate-500">
        <span />
        <span>{t('Declared')}</span>
        <span>{t('On the FDR copy')}</span>
        <span>{t('Bank confirmed')}</span>
      </div>
      {rows.map(([label, a, b, c], i) => (
        <div key={label} className="grid grid-cols-[1fr_1.2fr_1.2fr_1.2fr] border-b border-slate-100 px-4 py-2 last:border-0">
          <span className="text-slate-500">{label}</span>
          <span className="figure text-brand-900">{a}</span>
          <span className={i === 0 ? 'figure font-semibold text-seal-600 line-through decoration-seal-500/60' : 'figure text-brand-900'}>{b}</span>
          <span className="figure text-ink-green-700">{c}</span>
        </div>
      ))}
      <div className="border-t border-seal-100 bg-seal-50 px-4 py-2 text-[13px] text-seal-700">
        {t('Document differs from declaration: the copy shows one tenth of the amount.')}
      </div>
    </div>
  )
}

export default function Login() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const demo = useQuery({
    queryKey: ['demo-accounts'],
    queryFn: () => api.get<DemoAccounts>('/auth/demo-accounts'),
    retry: false,
    staleTime: Infinity,
  })
  const from = (location.state as { from?: string } | null)?.from ?? '/'
  if (user) return <Navigate to={from} replace />

  const submit = async (e?: FormEvent, override?: { email: string; password: string }) => {
    e?.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(override?.email ?? email, override?.password ?? password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <div className="hidden border-r border-slate-300 bg-canvas p-12 lg:flex lg:flex-col">
        <div className="flex items-center gap-3">
          <svg viewBox="0 0 36 36" className="size-11" aria-hidden>
            <path d="M5 7h18l6 6v16H5z" fill="#123f3c" />
            <path d="M23 7v6h6" fill="#1f5f5a" />
            <path d="M8.5 15c2.2-1.8 4.4 1.8 6.6 0s4.4 1.8 6.6 0M8.5 19c2.2-1.8 4.4 1.8 6.6 0s4.4 1.8 6.6 0" fill="none" stroke="#a9cfcb" strokeWidth="1.2" />
            <circle cx="24.5" cy="25.5" r="6" fill="#f5f7f7" stroke="#6a4fa8" strokeWidth="2.2" />
            <path d="M21.8 25.6l1.9 1.9 3.3-3.4" fill="none" stroke="#6a4fa8" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div className="leading-none">
            <div className="text-[26px] font-semibold text-brand-900" style={{ fontFamily: 'var(--font-display)', fontStretch: '85%' }}>
              Nidhi <span className="text-[17px] font-medium text-slate-400">निधि</span>
            </div>
            <div className="mt-1 text-[13px] text-slate-500">{t('Security deposits and FDRs held by AICTE')}</div>
          </div>
        </div>
        <div className="mt-auto max-w-xl">
          <h1 className="text-[44px] leading-[1.08] font-semibold text-brand-900" style={{ fontStretch: '84%' }}>
            {t('An FDR is security only if the bank says it is.')}
          </h1>
          <Specimen />
          <dl className="mt-8 space-y-4 border-t border-slate-300 pt-6">
            {POINTS.map(([title, text]) => (
              <div key={title}>
                <dt className="text-[16px] font-semibold text-brand-900">{title}</dt>
                <dd className="text-[15px] leading-snug text-slate-600">{text}</dd>
              </div>
            ))}
          </dl>
        </div>
        <p className="mt-12 text-[13px] text-slate-500">{t('Team SignalNine, Smart India Hackathon 2026, problem statement 26265 (AICTE)')}</p>
      </div>

      <div className="flex flex-col justify-center bg-white px-6 py-12 sm:px-12">
        <div className="mx-auto w-full max-w-md">
          <div className="mb-6 flex justify-end">
            <button
              onClick={() => setLang(isHindi ? 'en' : 'hi')}
              className="rounded-[5px] px-3 py-1 text-[14px] font-semibold text-brand-800 ring-1 ring-slate-300 ring-inset hover:bg-slate-50"
              lang={isHindi ? 'en' : 'hi'}
            >
              {isHindi ? 'English' : 'हिंदी'}
            </button>
          </div>
          <h2 className="text-[30px] font-semibold text-brand-900">{t('Sign in')}</h2>
          <p className="mt-1 text-[15px] text-slate-500">{t('AICTE officials and institutions with an approved account.')}</p>
          <form onSubmit={submit} className="mt-8 space-y-4">
            <Field label={t('Email')}>
              <Input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </Field>
            <Field label={t('Password')}>
              <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </Field>
            {error && <p className="rounded-lg bg-seal-50 px-3 py-2 text-sm text-seal-700">{error}</p>}
            <Button type="submit" variant="primary" className="w-full" loading={busy}>
              {t('Sign in')}
            </Button>
          </form>

          {demo.data && (
            <div className="mt-10">
              <div className="mb-2 flex items-baseline justify-between">
                <span className="text-[15px] font-semibold text-brand-900">{t('Try a role')}</span>
                <span className="text-[13px] text-slate-500">{t('password')} {demo.data.password}</span>
              </div>
              <div className="sheet divide-y divide-slate-100 overflow-hidden">
                {demo.data.accounts.map((a) => (
                  <button
                    key={a.email}
                    disabled={busy}
                    onClick={() => submit(undefined, { email: a.email, password: demo.data!.password })}
                    className="group flex w-full items-center gap-3 px-3.5 py-2.5 text-left hover:bg-brand-50/60"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-[15px] font-semibold text-brand-900">{a.role === 'INSTITUTION' ? a.full_name.replace('Principal, ', '') : ROLE[a.role]}{a.unit && a.role !== 'INSTITUTION' ? `, ${a.unit}` : ''}</span>
                      </div>
                      <div className="truncate text-[13px] text-slate-500">{t(a.hint ?? a.designation)}</div>
                    </div>
                    <ArrowRight className="size-4 text-slate-300 group-hover:text-brand-600" />
                  </button>
                ))}
              </div>
            </div>
          )}
          <p className="mt-8 text-center text-sm text-slate-500">
            {t('Holding a letter from the portal?')}{' '}
            <Link to="/verify" className="font-medium text-brand-700 hover:underline">
              {t('Verify it')}
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
