import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { ArrowLeft, Download, MapPin } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import InstrumentTable from '@/components/InstrumentTable'
import { Badge, Button, Card, CardHeader, ErrorState, KeyValue, Loading, Stat } from '@/components/ui'
import { api, download, errorMessage } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDate, fmtLakh, fmtNumber } from '@/lib/format'
import { t } from '@/lib/i18n'
import { PURPOSE, STATUS } from '@/lib/labels'
import type { Institution, InstrumentItem } from '@/lib/types'

interface Profile extends Institution {
  aliases: { alias: string; source: string }[]
  instruments: InstrumentItem[]
  chains: { purpose: string; approval_year: string; instruments: InstrumentItem[] }[]
  deposit_rules: { purpose: string; amount: number; min_tenure_months: number }[]
  lien_holder: string
}

/** One deposit requirement over the years: each FDR and the one that replaced it. */
function Chain({ c }: { c: Profile['chains'][number] }) {
  return (
    <div className="border-b border-slate-100 px-4 py-3 last:border-0">
      <div className="mb-2 text-[14px] text-slate-600">{PURPOSE[c.purpose]} · {t('from')} {c.approval_year}</div>
      <ol className="flex flex-wrap items-stretch gap-1">
        {c.instruments.map((x, i) => (
          <li key={x.id} className="flex items-stretch">
            {i > 0 && (
              <span className={clsx('flex items-center px-1 text-[12px]', c.instruments[i - 1].renewed_late ? 'text-seal-600' : 'text-ink-green-700')}
                title={c.instruments[i - 1].renewed_late ? t('Replacement lodged after maturity') : t('Replacement lodged before maturity')}>
                {c.instruments[i - 1].renewed_late ? t('late') : '→'}
              </span>
            )}
            <Link to={`/instruments/${x.id}`} className={clsx('block rounded-[4px] border px-2.5 py-1.5 hover:border-brand-400', ['ACTIVE', 'EXPIRING', 'MATURED', 'RELEASE_REQUESTED'].includes(x.status) ? 'border-brand-300 bg-brand-50' : 'border-slate-200 bg-white')}>
              <span className="figure block text-[14px] text-brand-900">{fmtLakh(x.amount)}</span>
              <span className="block text-[12px] text-slate-500">{x.bank?.short_name} · {fmtDate(x.issue_date).replace(/^\d+ /, '')} – {fmtDate(x.maturity_date).replace(/^\d+ /, '')}</span>
              <span className="block text-[12px]" style={{}}>{STATUS[x.status].label}</span>
            </Link>
          </li>
        ))}
      </ol>
    </div>
  )
}

export default function InstitutionProfile() {
  const { id } = useParams()
  const { isStaff } = useAuth()
  const { data: p, error, refetch } = useQuery({ queryKey: ['institution', Number(id)], queryFn: () => api.get<Profile>(`/institutions/${id}`) })
  if (error) return <ErrorState error={error} retry={refetch} />
  if (!p) return <Loading />
  const s = p.stats
  const exportHistory = async (format: 'pdf' | 'xlsx') => {
    try {
      await download(`/reports/institution/${p.id}`, { format }, `deposit-history.${format}`)
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }
  return (
    <div>
      {isStaff && (
        <Link to="/institutions" className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800">
          <ArrowLeft className="size-4" /> {t('Institutions')}
        </Link>
      )}
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span className="tabular font-medium text-slate-700">AICTE PID {p.aicte_pid}</span>
            <Badge>{p.inst_type}</Badge>
            <Badge>{p.ownership}</Badge>
            {p.approval_status !== 'APPROVED' && <Badge className="bg-turmeric-50 text-turmeric-700 ring-turmeric-100">{p.approval_status.replace('_', ' ').toLowerCase()}</Badge>}
          </div>
          <h1 className="mt-2 text-[30px] leading-tight font-semibold text-brand-900" style={{ fontStretch: '88%' }}>{p.name}</h1>
          <p className="mt-1 flex items-center gap-1 text-[15px] text-slate-600"><MapPin className="size-4" /> {p.city}, {p.state_name} · {p.region?.name}</p>
          {p.society_name && <p className="text-[14px] text-slate-500">{t('Run by')} {p.society_name}</p>}
        </div>
        <div className="flex gap-2">
          <Button size="sm" icon={<Download className="size-4" />} onClick={() => exportHistory('pdf')}>{t('Deposit history (PDF)')}</Button>
          <Button size="sm" onClick={() => exportHistory('xlsx')}>{t('Excel')}</Button>
        </div>
      </div>
      {s && (
        <div className="mb-6 grid grid-cols-2 gap-x-6 gap-y-5 md:grid-cols-5">
          <Stat label={t('Held by AICTE')} value={fmtLakh(s.held_amount)} hint={t('{n} instruments', { n: s.held })} />
          <Stat label={t('Matured, not renewed')} value={fmtNumber(s.matured_unrenewed)} tone={s.matured_unrenewed ? 'danger' : 'default'} />
          <Stat label={t('Maturing in 90 days')} value={fmtNumber(s.expiring)} tone={s.expiring ? 'warning' : 'default'} />
          <Stat label={t('Open discrepancies')} value={fmtNumber(s.open_discrepancies)} tone={s.open_discrepancies ? 'danger' : 'default'} />
          <Stat label={t('Renewed late')} value={s.renewals ? `${s.renewed_late} / ${s.renewals}` : '—'} hint={t('of past renewals')} />
        </div>
      )}
      <div className="grid gap-5 xl:grid-cols-[1.6fr_1fr]">
        <div className="min-w-0 space-y-5">
          <Card>
            <CardHeader title={t('Renewal history')} subtitle={t('Each requirement, from the first FDR to the one held now. Red marks a replacement lodged after maturity.')} />
            {p.chains.length ? p.chains.map((c, i) => <Chain key={i} c={c} />) : <p className="px-4 py-4 text-slate-500">{t('No deposits on record.')}</p>}
          </Card>
          <Card>
            <CardHeader title={t('All instruments')} />
            <InstrumentTable items={p.instruments} showInstitution={false} compact />
          </Card>
        </div>
        <div className="space-y-5">
          <Card>
            <CardHeader title={t('What this institution must keep')} subtitle={t('Demonstration norms')} />
            <dl className="divide-y divide-slate-100">
              {p.deposit_rules.map((r) => (
                <div key={r.purpose} className="flex items-baseline justify-between px-4 py-2 text-[14px]">
                  <dt className="text-slate-600">{PURPOSE[r.purpose]}</dt>
                  <dd className="figure text-brand-900">{fmtLakh(r.amount)} · {r.min_tenure_months} {t('months')}</dd>
                </div>
              ))}
              <div className="px-4 py-2 text-[13px] text-slate-500">{t('Lien in favour of')} {p.lien_holder}</div>
            </dl>
          </Card>
          <Card>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-4">
              <KeyValue label={t('Established')}>{p.established_year ?? '—'}</KeyValue>
              <KeyValue label={t('Approved intake')}>{fmtNumber(p.approved_intake)}</KeyValue>
              <KeyValue label={t('Email')} className="col-span-2 break-all">{p.email ?? '—'}</KeyValue>
              <KeyValue label={t('Phone')}>{p.phone ?? '—'}</KeyValue>
              <KeyValue label={t('Address')} className="col-span-2">{p.address ?? '—'}</KeyValue>
            </dl>
          </Card>
        </div>
      </div>
    </div>
  )
}
