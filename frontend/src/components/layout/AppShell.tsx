import { useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  BadgeCheck,
  Bell,
  BookOpenCheck,
  Building2,
  CalendarClock,
  ChartColumnBig,
  FileText,
  Landmark,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquareText,
  Plus,
  QrCode,
  Search,
  Settings2,
  ShieldCheck,
  Stamp,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { timeAgo } from '@/lib/format'
import { useDebounced, useHealth } from '@/lib/hooks'
import { isHindi, setLang, t } from '@/lib/i18n'
import { ALERT_KIND, ROLE, SEVERITY } from '@/lib/labels'
import { useLiveUpdates, type LiveState } from '@/lib/live'
import type { AlertItem, InstrumentItem, Institution, Page } from '@/lib/types'
import { ButtonLink } from '../ui'

interface NavItem {
  to: string
  label: string
  icon: ReactNode
  badge?: number
  show?: boolean
}

function Logo() {
  return (
    <Link to="/" className="group flex items-center gap-3" aria-label="Nidhi home">
      <svg viewBox="0 0 36 36" className="size-9 shrink-0" aria-hidden>
        {/* a deposit receipt with security-print lines, and the AICTE stamp over its corner */}
        <path d="M5 7h18l6 6v16H5z" fill="#123f3c" />
        <path d="M23 7v6h6" fill="#1f5f5a" />
        <path d="M8.5 15c2.2-1.8 4.4 1.8 6.6 0s4.4 1.8 6.6 0M8.5 19c2.2-1.8 4.4 1.8 6.6 0s4.4 1.8 6.6 0" fill="none" stroke="#a9cfcb" strokeWidth="1.2" />
        <circle cx="24.5" cy="25.5" r="6" fill="#f5f7f7" stroke="#6a4fa8" strokeWidth="2.2" />
        <path d="M21.8 25.6l1.9 1.9 3.3-3.4" fill="none" stroke="#6a4fa8" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <div className="leading-none">
        <div className="text-[22px] font-semibold text-brand-900" style={{ fontFamily: 'var(--font-display)', fontStretch: '85%' }}>
          Nidhi <span className="text-[15px] font-medium text-slate-400">निधि</span>
        </div>
        <div className="mt-1 text-[12px] text-slate-500">{t('AICTE deposits & FDRs')}</div>
      </div>
    </Link>
  )
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { user, isStaff, isGlobal, logout } = useAuth()
  const unread = useQuery({ queryKey: ['unread'], queryFn: () => api.get<{ unread: number }>('/alerts/unread-count'), refetchInterval: 60_000 })
  const role = user?.role
  const groups: { title?: string; items: NavItem[] }[] = [
    {
      items: [
        { to: '/', label: t('My desk'), icon: <LayoutDashboard className="size-4.5" /> },
        { to: '/instruments', label: isStaff ? t('Deposits & FDRs') : t('Our deposits'), icon: <Landmark className="size-4.5" /> },
        { to: '/maturity', label: t('Maturity calendar'), icon: <CalendarClock className="size-4.5" />, show: isStaff },
        { to: '/releases', label: t('Releases'), icon: <Stamp className="size-4.5" />, show: isStaff },
        { to: '/institutions', label: t('Institutions'), icon: <Building2 className="size-4.5" />, show: isStaff },
        { to: '/alerts', label: t('Alerts'), icon: <Bell className="size-4.5" />, badge: unread.data?.unread },
        { to: '/ask', label: t('Ask'), icon: <MessageSquareText className="size-4.5" />, show: isStaff },
      ],
    },
    {
      title: t('Analysis'),
      items: [
        { to: '/overview', label: t('Overview'), icon: <ChartColumnBig className="size-4.5" />, show: isStaff },
        { to: '/reports', label: t('Reports'), icon: <FileText className="size-4.5" />, show: isStaff },
        { to: '/proof', label: t('Proof'), icon: <BadgeCheck className="size-4.5" />, show: isStaff },
      ],
    },
    {
      title: t('Records'),
      items: [
        { to: '/integrity', label: t('Integrity'), icon: <ShieldCheck className="size-4.5" />, show: isGlobal },
        { to: '/admin', label: t('Administration'), icon: <Settings2 className="size-4.5" />, show: isGlobal },
        { to: '/verify', label: t('Verify a letter'), icon: <QrCode className="size-4.5" /> },
      ],
    },
  ]
  const home = t(role === 'COMPETENT_AUTHORITY' ? 'Approvals' : role === 'AUDITOR' ? 'Oversight' : role === 'ADMIN' ? 'System'
    : role === 'RB_HEAD' ? 'Bureau position' : role === 'ACCOUNTS' ? 'Releases to execute' : role === 'INSTITUTION' ? 'Our desk' : 'My desk')
  return (
    <div className="flex h-full flex-col border-r border-slate-300 bg-white">
      <div className="px-5 pt-5 pb-5">
        <Logo />
      </div>
      <nav className="flex-1 overflow-y-auto px-3 pb-3">
        {groups.map((g, gi) => {
          const visible = g.items.filter((i) => i.show !== false)
          if (!visible.length) return null
          return (
            <div key={gi} className={clsx(gi > 0 && 'mt-4 border-t border-slate-200 pt-3')}>
              {g.title && <div className="px-3 pb-1 text-[12.5px] text-slate-400">{g.title}</div>}
              {visible.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    clsx(
                      'relative flex items-center gap-3 rounded-[5px] px-3 py-[7px] text-[15px] transition-colors',
                      isActive
                        ? 'bg-brand-50 font-semibold text-brand-900 before:absolute before:inset-y-1.5 before:left-0 before:w-[3px] before:rounded-full before:bg-brand-800'
                        : 'text-slate-600 hover:bg-slate-50 hover:text-brand-900',
                    )
                  }
                >
                  <span className="text-slate-400">{item.icon}</span>
                  <span className="flex-1">{item.to === '/' ? home : item.label}</span>
                  {!!item.badge && (
                    <span className="figure rounded-[3px] bg-slate-100 px-1.5 text-[13px] leading-5 font-semibold text-slate-600">
                      {item.badge > 999 ? '999+' : item.badge}
                    </span>
                  )}
                </NavLink>
              ))}
            </div>
          )
        })}
      </nav>
      {user && (
        <div className="border-t border-slate-200 px-5 py-4">
          <div className="truncate text-[15px] font-semibold text-brand-900">{user.full_name}</div>
          <div className="truncate text-[13px] text-slate-500">{user.institution ? `${user.institution.name}, ${user.institution.city}` : user.designation}</div>
          <div className="mt-2 flex items-center justify-between">
            <span className="text-[13px] text-slate-500">{ROLE[user.role]}</span>
            <button onClick={logout} className="flex items-center gap-1 text-[13px] text-slate-500 hover:text-brand-900">
              <LogOut className="size-3.5" /> {t('Sign out')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function LiveDot({ state }: { state: LiveState }) {
  const map = {
    live: ['bg-ink-green-500', t('Live')],
    connecting: ['bg-turmeric-400', t('Connecting')],
    offline: ['bg-slate-400', t('Offline')],
  } as const
  const [color, label] = map[state]
  return (
    <span className="hidden items-center gap-1.5 px-2 py-1 text-[13px] text-slate-500 sm:inline-flex" title={t('Real-time updates')}>
      <span className="relative flex size-2">
        {state === 'live' && <span className={clsx('absolute inline-flex size-full animate-ping rounded-full opacity-60', color)} />}
        <span className={clsx('relative inline-flex size-2 rounded-full', color)} />
      </span>
      {label}
    </span>
  )
}

function GlobalSearch() {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const term = useDebounced(q.trim(), 250)
  const navigate = useNavigate()
  const box = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const { isStaff } = useAuth()
  const cases = useQuery({
    queryKey: ['search-instruments', term],
    queryFn: () => api.get<Page<InstrumentItem>>('/instruments', { q: term, page_size: 5 }),
    enabled: term.length >= 2,
  })
  const insts = useQuery({
    queryKey: ['search-insts', term],
    queryFn: () => api.get<Page<Institution>>('/institutions', { q: term, page_size: 5, sort: 'name' }),
    enabled: term.length >= 2 && isStaff,
  })
  useEffect(() => {
    const onDoc = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false)
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        input.current?.focus()
        setOpen(true)
      }
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [])
  const go = (path: string) => {
    setOpen(false)
    setQ('')
    navigate(path)
  }
  return (
    <div ref={box} className="relative w-full max-w-md">
      <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
      <input
        ref={input}
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && term) go(`/instruments?q=${encodeURIComponent(term)}`)
          if (e.key === 'Escape') setOpen(false)
        }}
        placeholder={t('Search FDR number, reference, institution…')}
        className="w-full rounded-[5px] border-0 bg-white py-1.5 pr-14 pl-9 text-[15px] text-slate-900 ring-1 ring-slate-300 placeholder:text-slate-400 focus:ring-2 focus:ring-brand-500"
        aria-label={t('Search')}
      />
      <kbd className="pointer-events-none absolute top-1/2 right-2.5 hidden -translate-y-1/2 rounded border border-slate-300 bg-white px-1.5 text-[10px] text-slate-500 sm:block">
        Ctrl K
      </kbd>
      {open && term.length >= 2 && (
        <div className="absolute top-full right-0 left-0 z-40 mt-1.5 overflow-hidden rounded-[6px] border border-slate-300 bg-white shadow-[0_18px_40px_-18px_rgba(21,32,57,0.4)]">
          <div className="px-3 pt-2.5 pb-1 text-[13px] text-slate-400">{t('Deposits')}</div>
          {cases.data?.items.length ? (
            cases.data.items.map((c) => (
              <button key={c.id} onClick={() => go(`/instruments/${c.id}`)} className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-slate-50">
                <span className="file-no text-xs">{c.ref_no}</span>
                <span className="truncate text-sm text-slate-700">{c.institution.name}</span>
                <span className="ml-auto shrink-0 text-xs text-slate-500 tabular">{c.fdr_number}</span>
              </button>
            ))
          ) : (
            <div className="px-3 py-2 text-sm text-slate-400">{t(cases.isFetching ? 'Searching…' : 'No deposits')}</div>
          )}
          {isStaff && <><div className="border-t border-slate-100 px-3 pt-2.5 pb-1 text-[13px] text-slate-400">{t('Institutions')}</div>
          {insts.data?.items.length ? (
            insts.data.items.map((i) => (
              <button key={i.id} onClick={() => go(`/institutions/${i.id}`)} className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-slate-50">
                <Building2 className="size-4 shrink-0 text-slate-400" />
                <span className="truncate text-sm text-slate-700">{i.name}</span>
                <span className="ml-auto shrink-0 text-xs text-slate-500">{i.city} · {i.aicte_pid}</span>
              </button>
            ))
          ) : (
            <div className="px-3 py-2 text-sm text-slate-400">{t(insts.isFetching ? 'Searching…' : 'No institutions')}</div>
          )}</>}
          <button onClick={() => go(`/instruments?q=${encodeURIComponent(term)}`)} className="w-full border-t border-slate-100 px-3 py-2 text-left text-sm font-medium text-brand-700 hover:bg-slate-50">
            See all results for “{term}”
          </button>
        </div>
      )}
    </div>
  )
}

function Notifications() {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const qc = useQueryClient()
  const navigate = useNavigate()
  const unread = useQuery({ queryKey: ['unread'], queryFn: () => api.get<{ unread: number }>('/alerts/unread-count'), refetchInterval: 60_000 })
  const list = useQuery({
    queryKey: ['alerts', 'bell'],
    queryFn: () => api.get<Page<AlertItem>>('/alerts', { page_size: 8 }),
    enabled: open,
  })
  useEffect(() => {
    const onDoc = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false)
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])
  const openAlert = async (a: AlertItem) => {
    setOpen(false)
    await api.post(`/alerts/${a.id}/read`).catch(() => undefined)
    qc.invalidateQueries({ queryKey: ['unread'] })
    if (a.instrument_id) navigate(`/instruments/${a.instrument_id}`)
  }
  const count = unread.data?.unread ?? 0
  return (
    <div ref={box} className="relative">
      <button onClick={() => setOpen((v) => !v)} className="relative rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-700" aria-label={`Alerts (${count} unread)`}>
        <Bell className="size-5" />
        {count > 0 && (
          <span className="figure absolute -top-0.5 -right-1 min-w-4.5 rounded-[3px] bg-brand-800 px-1 text-center text-[11px] leading-4.5 font-semibold text-white">
            {count > 99 ? '99+' : count}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-[min(92vw,24rem)] overflow-hidden rounded-[6px] border border-slate-300 bg-white shadow-[0_18px_40px_-18px_rgba(21,32,57,0.4)]">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
            <span className="text-sm font-semibold">{t('Alerts')}</span>
            <button
              className="text-xs font-medium text-brand-700 hover:underline"
              onClick={async () => {
                await api.post('/alerts/read-all')
                qc.invalidateQueries({ queryKey: ['unread'] })
                qc.invalidateQueries({ queryKey: ['alerts'] })
              }}
            >
              {t('Mark all read')}
            </button>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {list.data?.items.map((a) => (
              <button key={a.id} onClick={() => openAlert(a)} className={clsx('flex w-full gap-3 border-b border-slate-50 px-4 py-3 text-left hover:bg-slate-50', !a.read && 'bg-brand-50/40')}>
                <span className={clsx('mt-1.5 size-2 shrink-0 rounded-full', SEVERITY[a.severity].dot)} />
                <span className="min-w-0">
                  <span className="block text-[11px] font-medium text-slate-500">
                    {ALERT_KIND[a.kind] ?? a.kind} · {timeAgo(a.created_at)}
                  </span>
                  <span className="block text-sm font-medium text-slate-800">{a.title}</span>
                  <span className="line-clamp-2 block text-xs text-slate-500">{a.message}</span>
                </span>
              </button>
            ))}
            {list.data && list.data.items.length === 0 && <div className="px-4 py-8 text-center text-sm text-slate-500">{t("You're all caught up.")}</div>}
          </div>
          <Link to="/alerts" onClick={() => setOpen(false)} className="block border-t border-slate-100 px-4 py-2.5 text-center text-sm font-medium text-brand-700 hover:bg-slate-50">
            {t('View all alerts')}
          </Link>
        </div>
      )}
    </div>
  )
}

export default function AppShell() {
  const { canLodge, isInstitution } = useAuth()
  const live = useLiveUpdates()
  const health = useHealth()
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  useEffect(() => setMobileOpen(false), [location.pathname])

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 lg:block">
        <Sidebar />
      </aside>
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setMobileOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-72">
            <Sidebar onNavigate={() => setMobileOpen(false)} />
            <button onClick={() => setMobileOpen(false)} className="absolute top-4 -right-10 rounded-full bg-white p-1.5" aria-label={t('Close menu')}>
              <X className="size-5" />
            </button>
          </div>
        </div>
      )}
      <div className="lg:pl-64">
        {health.data?.demo_mode && (
          <div className="no-print flex items-center justify-center gap-2 border-b border-buff-200 bg-buff-100 px-4 py-1 text-center text-[13px] text-buff-700">
            <BookOpenCheck className="size-3.5" />
            {t('Demonstration data. Every institution, bank, person and deposit shown is fictional.')}
          </div>
        )}
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-slate-300 bg-canvas/95 px-4 backdrop-blur sm:px-8">
          <button className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setMobileOpen(true)} aria-label={t('Open menu')}>
            <Menu className="size-5" />
          </button>
          <GlobalSearch />
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => setLang(isHindi ? 'en' : 'hi')}
              className="rounded-[5px] px-2.5 py-1 text-[14px] font-semibold text-brand-800 ring-1 ring-slate-300 ring-inset hover:bg-white"
              title={isHindi ? 'Switch to English' : 'हिंदी में देखें'}
              lang={isHindi ? 'en' : 'hi'}
            >
              {isHindi ? 'English' : 'हिंदी'}
            </button>
            <LiveDot state={live} />
            <Notifications />
            {canLodge && (
              <ButtonLink to="/instruments/new" variant="primary" size="sm" icon={<Plus className="size-4" />}>
                <span className="hidden sm:inline">{isInstitution ? t('Lodge an FDR') : t('Lodge on behalf')}</span>
              </ButtonLink>
            )}
          </div>
        </header>
        <main className="mx-auto max-w-[1440px] px-4 py-7 sm:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
