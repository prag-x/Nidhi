import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, ShieldCheck, UserPlus } from 'lucide-react'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Badge, Button, Card, CardHeader, Field, Input, Loading, Modal, PageHeader, Pagination, Select, Tabs, Toggle } from '@/components/ui'
import { api, errorMessage } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDateTime, fmtNumber, timeAgo } from '@/lib/format'
import { useMeta } from '@/lib/hooks'
import { PURPOSE, ROLE } from '@/lib/labels'
import type { Role, User, UserRef } from '@/lib/types'
import { t } from '@/lib/i18n'

type Tab = 'users' | 'norms' | 'rules' | 'outbox' | 'audit' | 'system'

function Users({ canEdit }: { canEdit: boolean }) {
  const qc = useQueryClient()
  const meta = useMeta()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ email: '', full_name: '', designation: '', role: 'RB_OFFICER', org_unit_id: '', institution_id: '', password: '' })
  const users = useQuery({ queryKey: ['admin', 'users'], queryFn: () => api.get<User[]>('/admin/users') })
  const create = useMutation({
    mutationFn: () => api.post('/admin/users', { ...form, org_unit_id: form.org_unit_id ? Number(form.org_unit_id) : null, institution_id: form.institution_id ? Number(form.institution_id) : null }),
    onSuccess: () => { toast.success('User created'); setOpen(false); qc.invalidateQueries({ queryKey: ['admin', 'users'] }) },
    onError: (e) => toast.error(errorMessage(e)),
  })
  const toggle = useMutation({
    mutationFn: (u: User) => api.patch(`/admin/users/${u.id}`, { is_active: !u.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
    onError: (e) => toast.error(errorMessage(e)),
  })
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }))
  return (
    <Card>
      <CardHeader title={t('Users')} subtitle={t('AICTE officials by role, and institution users who lodge and track their own deposits.')}
        actions={canEdit && <Button size="sm" variant="primary" icon={<UserPlus className="size-4" />} onClick={() => setOpen(true)}>{t('Add user')}</Button>} />
      {users.isLoading ? <Loading /> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead><tr className="border-b border-slate-100 text-left text-xs text-slate-500">
              <th className="px-4 py-2 font-medium">{t('Name')}</th><th className="px-3 py-2 font-medium">{t('Role')}</th><th className="px-3 py-2 font-medium">{t('Unit or institution')}</th>
              <th className="px-3 py-2 font-medium">{t('Last sign-in')}</th><th className="px-4 py-2 font-medium">{t('Status')}</th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100">
              {users.data?.map((u) => (
                <tr key={u.id}>
                  <td className="px-4 py-2.5"><div className="font-medium text-slate-800">{u.full_name}</div><div className="text-xs text-slate-500">{u.designation} · {u.email}</div></td>
                  <td className="px-3 py-2.5 text-slate-600">{ROLE[u.role]}</td>
                  <td className="px-3 py-2.5 text-slate-600">{u.institution ? `${u.institution.name}, ${u.institution.city}` : u.org_unit?.name ?? '—'}</td>
                  <td className="px-3 py-2.5 text-slate-500">{u.last_login_at ? timeAgo(u.last_login_at) : 'Never'}</td>
                  <td className="px-4 py-2.5">
                    {canEdit ? <Toggle checked={u.is_active} onChange={() => toggle.mutate(u)} label={u.is_active ? 'Active' : 'Disabled'} />
                      : <Badge>{u.is_active ? 'Active' : 'Disabled'}</Badge>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Modal open={open} onClose={() => setOpen(false)} title={t('Add user')}
        footer={<><Button onClick={() => setOpen(false)}>{t('Cancel')}</Button><Button variant="primary" loading={create.isPending} onClick={() => create.mutate()}>{t('Create')}</Button></>}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t('Full name')} required><Input value={form.full_name} onChange={set('full_name')} /></Field>
          <Field label={t('Designation')} required><Input value={form.designation} onChange={set('designation')} /></Field>
          <Field label={t('Email')} required><Input type="email" value={form.email} onChange={set('email')} /></Field>
          <Field label={t('Role')} required>
            <Select value={form.role} onChange={set('role')}>
              {(Object.keys(ROLE) as Role[]).map((r) => <option key={r} value={r}>{ROLE[r]}</option>)}
            </Select>
          </Field>
          <Field label={t('Unit')}>
            <Select value={form.org_unit_id} onChange={set('org_unit_id')}>
              <option value="">{t('None')}</option>
              {meta.data?.units.map((u) => <option key={u.id} value={u.id}>{u.code} — {u.name}</option>)}
            </Select>
          </Field>
          {form.role === 'INSTITUTION' && (
            <Field label={t('Institution ID')} hint={t('From the institution’s page address')}><Input value={form.institution_id} onChange={set('institution_id')} inputMode="numeric" /></Field>
          )}
          <Field label={t('Initial password')} required hint={t('8+ characters with a letter, digit and symbol')}><Input type="password" value={form.password} onChange={set('password')} /></Field>
        </div>
      </Modal>
    </Card>
  )
}

interface Rule { id: number; purpose: string; inst_type: string; amount: number; min_tenure_months: number; note: string | null }

function Norms({ canEdit }: { canEdit: boolean }) {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['admin', 'rules'], queryFn: () => api.get<Rule[]>('/admin/deposit-rules') })
  const save = useMutation({
    mutationFn: (r: Rule) => api.patch(`/admin/deposit-rules/${r.id}`, r),
    onSuccess: () => { toast.success(t('Norm updated for deposits lodged from now on')); qc.invalidateQueries({ queryKey: ['admin', 'rules'] }); qc.invalidateQueries({ queryKey: ['meta'] }) },
    onError: (e) => toast.error(errorMessage(e)),
  })
  if (!data) return <Loading />
  return (
    <Card>
      <CardHeader title={t('Deposit norms')} subtitle={t('Amount and minimum validity checked for every new deposit, by purpose and type of institution. Demonstration values: set them to the figures in force.')} />
      <table className="w-full text-sm">
        <thead><tr className="border-b border-slate-100 text-left text-xs text-slate-500">
          <th className="px-4 py-2 font-medium">{t('Purpose')}</th><th className="px-3 py-2 font-medium">{t('Institution type')}</th>
          <th className="px-3 py-2 text-right font-medium">{t('Amount (₹)')}</th><th className="px-4 py-2 text-right font-medium">{t('Months valid')}</th>
        </tr></thead>
        <tbody className="divide-y divide-slate-100">
          {data.map((r) => (
            <tr key={r.id}>
              <td className="px-4 py-2">{PURPOSE[r.purpose] ?? r.purpose}</td>
              <td className="px-3 py-2 text-slate-600">{r.inst_type === '*' ? t('Any') : r.inst_type}</td>
              <td className="px-3 py-2 text-right">
                <Input type="number" defaultValue={r.amount} disabled={!canEdit} className="ml-auto w-32 py-1 text-right" aria-label={t('Amount')}
                  onBlur={(e) => Number(e.target.value) !== r.amount && save.mutate({ ...r, amount: Number(e.target.value) })} />
              </td>
              <td className="px-4 py-2 text-right">
                <Input type="number" defaultValue={r.min_tenure_months} disabled={!canEdit} className="ml-auto w-20 py-1 text-right" aria-label={t('Months')}
                  onBlur={(e) => Number(e.target.value) !== r.min_tenure_months && save.mutate({ ...r, min_tenure_months: Number(e.target.value) })} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

function Outbox() {
  const [page, setPage] = useState(1)
  const { data } = useQuery({
    queryKey: ['admin', 'outbox', page],
    queryFn: () => api.get<{ total: number; items: { id: number; channel: string; recipient: string; subject: string; body: string; status: string; created_at: string; instrument_id: number | null }[] }>('/admin/notifications', { page, page_size: 50 }),
    placeholderData: keepPreviousData,
  })
  return (
    <Card>
      <CardHeader title={t('Messages sent to institutions')} subtitle={t('Every reminder, acknowledgement and rectification notice, by email and SMS. In the demonstration nothing leaves the server; this is the outbox a mail and SMS gateway would read.')} />
      <ul className="divide-y divide-slate-100">
        {data?.items.map((n) => (
          <li key={n.id} className="px-4 py-2.5 text-sm">
            <div className="flex flex-wrap items-baseline gap-2">
              <Badge>{n.channel}</Badge>
              <span className="font-medium text-slate-800">{n.subject}</span>
              <span className="text-xs text-slate-500">{n.recipient} · {fmtDateTime(n.created_at)}</span>
            </div>
            <p className="mt-0.5 text-slate-600">{n.body}</p>
          </li>
        ))}
      </ul>
      {data && <Pagination page={page} pageSize={50} total={data.total} onChange={setPage} />}
    </Card>
  )
}

function Rules({ canEdit }: { canEdit: boolean }) {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['admin', 'settings'], queryFn: () => api.get<{ key: string; label: string; value: number | boolean | string; default: number | boolean | string }[]>('/admin/settings') })
  const save = useMutation({
    mutationFn: ({ key, value }: { key: string; value: number | boolean | string }) => api.put(`/admin/settings/${key}`, { value }),
    onSuccess: () => { toast.success('Rule updated'); qc.invalidateQueries({ queryKey: ['admin', 'settings'] }) },
    onError: (e) => toast.error(errorMessage(e)),
  })
  if (!data) return <Loading />
  return (
    <Card>
      <CardHeader title={t('Reminders, escalation and checks')} subtitle={t('How the monitor and the checks behave. Every change is audited.')} />
      <ul className="divide-y divide-slate-100">
        {data.map((s) => (
          <li key={s.key} className="flex flex-wrap items-center gap-3 px-4 py-3">
            <div className="min-w-0 flex-1">
              <div className="text-sm text-slate-800">{s.label}</div>
              <div className="text-xs text-slate-400">default {String(s.default)}</div>
            </div>
            {typeof s.value === 'boolean' ? (
              <Toggle checked={s.value} onChange={(v) => canEdit && save.mutate({ key: s.key, value: v })} label={s.value ? 'On' : 'Off'} />
            ) : typeof s.value === 'string' ? (
              <Input defaultValue={s.value} disabled={!canEdit} className="w-64 py-1" aria-label={s.label}
                onBlur={(e) => e.target.value !== s.value && save.mutate({ key: s.key, value: e.target.value })} />
            ) : (
              <Input type="number" step={Number.isInteger(s.default) ? 1 : 0.01} defaultValue={s.value} disabled={!canEdit} className="w-24 py-1 text-right"
                onBlur={(e) => Number(e.target.value) !== s.value && save.mutate({ key: s.key, value: Number(e.target.value) })} aria-label={s.label} />
            )}
          </li>
        ))}
      </ul>
    </Card>
  )
}

function Audit() {
  const [action, setAction] = useState('')
  const [page, setPage] = useState(1)
  const { data } = useQuery({
    queryKey: ['admin', 'audit', action, page],
    queryFn: () => api.get<{ total: number; actions: string[]; items: { id: number; at: string; user: UserRef | null; action: string; entity_type: string | null; entity_id: string | null; ip: string | null; details: Record<string, unknown> | null }[] }>('/admin/audit', { action, page, page_size: 50 }),
    placeholderData: keepPreviousData,
  })
  return (
    <Card>
      <CardHeader title={t('Audit log')} subtitle={t('Sign-ins, every action on a deposit, exports and configuration changes')}
        actions={<Select value={action} onChange={(e) => { setAction(e.target.value); setPage(1) }} className="w-auto py-1 text-xs" aria-label={t('Action')}>
          <option value="">{t('All actions')}</option>{data?.actions.map((a) => <option key={a} value={a}>{a}</option>)}
        </Select>} />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm">
          <thead><tr className="border-b border-slate-100 text-left text-xs text-slate-500">
            <th className="px-4 py-2 font-medium">{t('When')}</th><th className="px-3 py-2 font-medium">{t('Who')}</th><th className="px-3 py-2 font-medium">{t('Action')}</th><th className="px-3 py-2 font-medium">{t('Record')}</th><th className="px-4 py-2 font-medium">{t('Details')}</th>
          </tr></thead>
          <tbody className="divide-y divide-slate-100">
            {data?.items.map((r) => (
              <tr key={r.id} className="align-top">
                <td className="px-4 py-2 whitespace-nowrap text-slate-500">{fmtDateTime(r.at)}</td>
                <td className="px-3 py-2">{r.user?.full_name ?? '—'}<div className="text-xs text-slate-400">{r.ip}</div></td>
                <td className="px-3 py-2 font-mono text-xs">{r.action}</td>
                <td className="px-3 py-2 text-xs text-slate-600">{r.entity_type ? `${r.entity_type} #${r.entity_id}` : '—'}</td>
                <td className="max-w-md px-4 py-2 font-mono text-[11px] break-all text-slate-500">{r.details ? JSON.stringify(r.details) : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data && <Pagination page={page} pageSize={50} total={data.total} onChange={setPage} />}
    </Card>
  )
}

function System() {
  const qc = useQueryClient()
  const integrity = useMutation({ mutationFn: () => api.get<{ instruments_checked: number; valid: number; broken: { ref_no: string; broken_at_seq: number }[] }>('/admin/integrity') })
  const sweep = useMutation({
    mutationFn: () => api.post<Record<string, number>>('/admin/sweep'),
    onSuccess: (r) => { toast.success(t('Monitor run complete'), { description: Object.entries(r).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`).join(' · ') }); qc.invalidateQueries() },
    onError: (e) => toast.error(errorMessage(e)),
  })
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
      <Card>
        <CardHeader title={t('History integrity')} subtitle={t('Re-computes the hash chain of every deposit history')} icon={<ShieldCheck className="size-4" />} />
        <div className="space-y-3 p-4">
          <Button loading={integrity.isPending} onClick={() => integrity.mutate()}>{t('Verify all deposit histories')}</Button>
          {integrity.data && (
            integrity.data.broken.length === 0 ? (
              <p className="rounded-lg bg-ink-green-50 px-3 py-2 text-sm text-ink-green-700">{t('All {n} deposit histories are intact.', { n: fmtNumber(integrity.data.instruments_checked) })}</p>
            ) : (
              <div className="rounded-lg bg-seal-50 px-3 py-2 text-sm text-seal-700">
                {integrity.data.broken.length} altered: {integrity.data.broken.map((b) => `${b.ref_no} (#${b.broken_at_seq})`).join(', ')}
              </div>
            )
          )}
        </div>
      </Card>
      <Card>
        <CardHeader title={t('Maturity monitor')} subtitle={t('Runs automatically every few minutes')} icon={<Activity className="size-4" />} />
        <div className="space-y-2 p-4 text-sm text-slate-600">
          <p>{t('Moves deposits to maturing and matured, sends reminders, escalates unrenewed FDRs, re-confirms held FDRs with banks online, chases bank replies and re-scores late-renewal risk.')}</p>
          <Button loading={sweep.isPending} onClick={() => sweep.mutate()}>{t('Run now')}</Button>
        </div>
      </Card>
    </div>
  )
}

export default function Admin() {
  const { user, isGlobal } = useAuth()
  const [params, setParams] = useSearchParams()
  const tab = (['users', 'norms', 'rules', 'outbox', 'audit', 'system'].includes(params.get('tab') ?? '') ? params.get('tab') : 'users') as Tab
  const setTab = (t: Tab) => setParams({ tab: t }, { replace: true })
  const canEdit = user?.role === 'ADMIN'
  if (!isGlobal) {
    return (
      <div>
        <PageHeader title={t('Administration')} />
        <p className="text-[15px] text-slate-600">{t('Administration is available to the administrator, the competent authority, the RB head and the auditor.')}</p>
      </div>
    )
  }
  return (
    <div>
      <PageHeader title={t('Administration')} subtitle={canEdit ? t('Users, deposit norms, reminders and escalation, the outbox and the audit log') : t('View only. Changes are made by the administrator.')} />
      <div className="mb-5"><Tabs value={tab} onChange={setTab} tabs={[
        { value: 'users', label: t('Users') }, { value: 'norms', label: t('Deposit norms') }, { value: 'rules', label: t('Reminders & checks') },
        { value: 'outbox', label: t('Outbox') }, { value: 'audit', label: t('Audit log') }, { value: 'system', label: t('System') },
      ]} /></div>
      {tab === 'users' && <Users canEdit={canEdit} />}
      {tab === 'norms' && <Norms canEdit={canEdit} />}
      {tab === 'outbox' && <Outbox />}
      {tab === 'rules' && <Rules canEdit={canEdit} />}
      {tab === 'audit' && <Audit />}
      {tab === 'system' && <System />}
    </div>
  )
}
