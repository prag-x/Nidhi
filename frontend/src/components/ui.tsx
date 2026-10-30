import clsx, { type ClassValue } from 'clsx'
import { ChevronLeft, ChevronRight, Loader2, X } from 'lucide-react'
import {
  forwardRef,
  useEffect,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'
import { createPortal } from 'react-dom'
import { twMerge } from 'tailwind-merge'
import { Link } from 'react-router-dom'
import { fmtNumber } from '@/lib/format'
import { SEVERITY, STATUS, VERIFICATION } from '@/lib/labels'
import type { Severity, Status, Verification } from '@/lib/types'
import { t } from '@/lib/i18n'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// ---------------------------------------------------------------- buttons

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'warning' | 'success'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-brand-800 text-white hover:bg-brand-900',
  secondary: 'bg-white text-brand-800 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 hover:ring-brand-300',
  ghost: 'text-slate-600 hover:bg-slate-100 hover:text-brand-800',
  danger: 'bg-seal-600 text-white hover:bg-seal-700',
  warning: 'bg-turmeric-400 text-brand-950 hover:bg-turmeric-500',
  success: 'bg-ink-green-600 text-white hover:bg-ink-green-700',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: 'xs' | 'sm' | 'md'
  loading?: boolean
  icon?: ReactNode
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', loading, icon, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-[5px] font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        size === 'xs' && 'px-2 py-1 text-xs',
        size === 'sm' && 'px-2.5 py-1 text-sm',
        size === 'md' && 'px-3.5 py-1.5 text-[15px]',
        VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  )
})

/** A link that looks like a button (a button inside a link is invalid HTML and confuses screen readers). */
export function ButtonLink({ to, variant = 'secondary', size = 'md', icon, className, children, ...rest }:
  { to: string; variant?: Variant; size?: 'xs' | 'sm' | 'md'; icon?: ReactNode; className?: string; children: ReactNode; title?: string }) {
  return (
    <Link
      to={to}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-[5px] font-semibold transition-colors',
        size === 'xs' && 'px-2 py-1 text-xs',
        size === 'sm' && 'px-2.5 py-1 text-sm',
        size === 'md' && 'px-3.5 py-1.5 text-[15px]',
        VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {icon}
      {children}
    </Link>
  )
}

// ---------------------------------------------------------------- surfaces

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <section className={cn('sheet min-w-0', className)}>{children}</section>
}

export function CardHeader({
  title,
  subtitle,
  actions,
  icon,
  className,
}: {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  icon?: ReactNode
  className?: string
}) {
  return (
    <div className={clsx('flex items-start justify-between gap-3 border-b border-slate-200 px-4 pt-3 pb-2.5', className)}>
      <div className="flex min-w-0 items-start gap-2.5">
        {icon && <div className="mt-1 text-slate-400">{icon}</div>}
        <div className="min-w-0">
          <h3 className="text-[17px] leading-snug font-semibold text-brand-900">{title}</h3>
          {subtitle && <p className="text-[13px] leading-snug text-slate-500">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}

export function PageHeader({
  title,
  subtitle,
  actions,
  eyebrow,
}: {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  eyebrow?: ReactNode
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3 border-b border-slate-300 pb-4">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-sm text-slate-500">{eyebrow}</div>}
        <h1 className="text-[28px] leading-tight font-semibold text-brand-900 sm:text-[34px]" style={{ fontStretch: '88%' }}>{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-[15px] text-slate-600">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

// ---------------------------------------------------------------- badges

export function Badge({ className, children, dot }: { className?: string; children: ReactNode; dot?: string }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-[3px] px-1.5 py-px text-[12px] font-semibold whitespace-nowrap ring-1 ring-inset',
        className ?? 'bg-slate-50 text-slate-600 ring-slate-200',
      )}
    >
      {dot && <span className={clsx('size-1.5 rounded-full', dot)} />}
      {children}
    </span>
  )
}

export function StatusBadge({ status }: { status: Status }) {
  const s = STATUS[status]
  return <Badge className={s.className} dot={s.dot}>{s.label}</Badge>
}

export function VerificationBadge({ status }: { status: Verification }) {
  const s = VERIFICATION[status]
  return <Badge className={s.className} dot={s.dot}>{s.label}</Badge>
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const s = SEVERITY[severity]
  return <Badge className={s.className}>{s.label}</Badge>
}

/** Days to maturity, coloured by urgency. */
export function MaturityBadge({ days, status }: { days: number; status?: Status }) {
  if (status && ['RENEWED', 'RELEASED', 'REJECTED'].includes(status)) return null
  const cls = days < 0 ? 'bg-seal-600 text-white ring-seal-600' : days <= 30 ? 'bg-seal-50 text-seal-700 ring-seal-100'
    : days <= 90 ? 'bg-turmeric-50 text-turmeric-700 ring-turmeric-100' : 'bg-white text-slate-600 ring-slate-300'
  const text = days < 0 ? t('Matured {n}d ago', { n: -days }) : days === 0 ? t('Matures today') : t('{n}d to maturity', { n: days })
  return <Badge className={cls}>{text}</Badge>
}

export function RefNo({ children }: { children: ReactNode }) {
  return <span className="file-no">{children}</span>
}

// ---------------------------------------------------------------- form controls

const control =
  'block w-full rounded-[5px] border-0 bg-white px-3 py-1.5 text-[15px] text-slate-900 ring-1 ring-inset ring-slate-300 placeholder:text-slate-400 focus:ring-2 focus:ring-inset focus:ring-brand-500 disabled:bg-slate-50 disabled:text-slate-500'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...rest },
  ref,
) {
  return <input ref={ref} className={cn(control, className)} {...rest} />
})

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea(
  { className, ...rest },
  ref,
) {
  return <textarea ref={ref} className={cn(control, 'min-h-20', className)} {...rest} />
})

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...rest },
  ref,
) {
  return (
    <select ref={ref} className={cn(control, 'max-w-full pr-8', className)} {...rest}>
      {children}
    </select>
  )
})

export function Field({
  label,
  hint,
  error,
  children,
  required,
  className,
}: {
  label: ReactNode
  hint?: ReactNode
  error?: string | null
  children: ReactNode
  required?: boolean
  className?: string
}) {
  return (
    <label className={clsx('block', className)}>
      <span className="mb-1 block text-[13px] font-semibold text-slate-700">
        {label}
        {required && <span className="text-seal-500"> *</span>}
      </span>
      {children}
      {error ? (
        <span className="mt-1 block text-xs text-seal-600">{error}</span>
      ) : (
        hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>
      )}
    </label>
  )
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode }) {
  const id = useId()
  return (
    <label htmlFor={id} className="inline-flex cursor-pointer items-center gap-2 text-sm text-slate-700 select-none">
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={clsx('relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors', checked ? 'bg-brand-700' : 'bg-slate-300')}
      >
        <span className={clsx('absolute top-0.5 size-4 rounded-full bg-white shadow transition-transform', checked ? 'translate-x-4.5' : 'translate-x-0.5')} />
      </button>
      {label}
    </label>
  )
}

// ---------------------------------------------------------------- feedback

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx('size-5 animate-spin text-slate-400', className)} />
}

export function Loading({ label = t('Loading…') }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-500">
      <Spinner /> {label}
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx('animate-pulse rounded-md bg-slate-200/70', className)} />
}

export function EmptyState({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      {icon && <div className="mb-3 text-slate-300">{icon}</div>}
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {children && <div className="mt-1 max-w-sm text-sm text-slate-500">{children}</div>}
    </div>
  )
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  return (
    <div className="m-4 rounded-[5px] border border-seal-100 bg-seal-50 p-4 text-sm text-seal-700">
      <p className="font-medium">{t('Could not load this view')}</p>
      <p className="mt-1">{error instanceof Error ? error.message : 'Unexpected error'}</p>
      {retry && (
        <Button size="sm" className="mt-3" onClick={retry}>
          {t('Try again')}
        </Button>
      )}
    </div>
  )
}

export function ProgressBar({ value, tone = 'bg-brand-600', className }: { value: number; tone?: string; className?: string }) {
  return (
    <div className={clsx('h-1.5 w-full overflow-hidden rounded-[2px] bg-slate-100', className)}>
      <div className={clsx('h-full rounded-[2px]', tone)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  )
}

// ---------------------------------------------------------------- overlay

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  description?: ReactNode
  children: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl'
}) {
  const panel = useRef<HTMLDivElement>(null)
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && closeRef.current()
    document.addEventListener('keydown', onKey)
    const prev = document.activeElement as HTMLElement | null
    setTimeout(() => {
      const root = panel.current
      const target =
        root?.querySelector<HTMLElement>('input:not([disabled]), select:not([disabled]), textarea:not([disabled])') ??
        root?.querySelector<HTMLElement>('[data-autofocus], footer button, button')
      target?.focus()
    }, 30)
    return () => {
      document.removeEventListener('keydown', onKey)
      prev?.focus?.()
    }
  }, [open])
  if (!open) return null
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-brand-950/40" onClick={onClose} />
      <div
        ref={panel}
        className={clsx(
          'relative flex max-h-[92vh] w-full flex-col rounded-t-lg border border-slate-300 bg-white shadow-[0_24px_60px_-20px_rgba(21,32,57,0.45)] sm:rounded-lg',
          size === 'sm' && 'sm:max-w-md',
          size === 'md' && 'sm:max-w-lg',
          size === 'lg' && 'sm:max-w-2xl',
          size === 'xl' && 'sm:max-w-4xl',
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-brand-900">{title}</h2>
            {description && <p className="mt-0.5 text-sm text-slate-500">{description}</p>}
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600" aria-label={t('Close')}>
            <X className="size-5" />
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-slate-100 bg-slate-50/60 px-5 py-3">{footer}</div>}
      </div>
    </div>,
    document.body,
  )
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { value: T; label: ReactNode; count?: number }[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div className="scrollbar-thin flex gap-1 overflow-x-auto border-b border-slate-200">
      {tabs.map((t) => (
        <button
          key={t.value}
          onClick={() => onChange(t.value)}
          className={clsx(
            '-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors',
            value === t.value ? 'border-brand-800 text-brand-900' : 'border-transparent text-slate-500 hover:text-brand-800',
          )}
        >
          {t.label}
          {t.count !== undefined && (
            <span className={clsx('rounded-full px-1.5 text-xs tabular', value === t.value ? 'bg-brand-100 text-brand-800' : 'bg-slate-100 text-slate-600')}>
              {fmtNumber(t.count)}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}

export function Pagination({
  page,
  pageSize,
  total,
  onChange,
}: {
  page: number
  pageSize: number
  total: number
  onChange: (page: number) => void
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (total === 0) return null
  const from = (page - 1) * pageSize + 1
  const to = Math.min(total, page * pageSize)
  return (
    <div className="flex items-center justify-between gap-3 border-t border-slate-100 px-4 py-2.5 text-sm text-slate-600">
      <span className="tabular">
        {fmtNumber(from)}–{fmtNumber(to)} of {fmtNumber(total)}
      </span>
      <div className="flex items-center gap-1">
        <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label={t('Previous page')}>
          <ChevronLeft className="size-4" />
        </Button>
        <span className="tabular px-1 text-xs text-slate-500">
          Page {page} / {pages}
        </span>
        <Button size="sm" variant="ghost" disabled={page >= pages} onClick={() => onChange(page + 1)} aria-label={t('Next page')}>
          <ChevronRight className="size-4" />
        </Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- KPI tile

export function Stat({
  label,
  value,
  hint,
  to,
  tone = 'default',
  icon,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  to?: string
  tone?: 'default' | 'warning' | 'danger' | 'success' | 'brand'
  icon?: ReactNode
}) {
  const tones = {
    default: 'text-brand-900',
    warning: 'text-turmeric-700',
    danger: 'text-seal-600',
    success: 'text-ink-green-700',
    brand: 'text-brand-800',
  }
  const body = (
    <div className="flex h-full flex-col gap-0.5 border-l-2 border-slate-300 py-1 pl-3 transition-colors group-hover:border-brand-700">
      <span className="flex items-center gap-1.5 text-[13px] text-slate-600">
        {icon && <span className="text-slate-400">{icon}</span>}
        {label}
      </span>
      <span className={clsx('figure text-[30px] leading-none font-semibold', tones[tone])}>{value}</span>
      {hint && <span className="text-[12.5px] leading-snug text-slate-500">{hint}</span>}
    </div>
  )
  return to ? (
    <Link to={to} className="group block h-full rounded-sm focus-visible:outline-2">
      {body}
    </Link>
  ) : (
    body
  )
}

export function KeyValue({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={clsx('min-w-0', className)}>
      <dt className="text-[13px] text-slate-500">{label}</dt>
      <dd className="text-[15px] text-slate-900">{children}</dd>
    </div>
  )
}

/** Shown when someone opens a page their role does not use, e.g. by typing its address. */
export function NotForRole({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <PageHeader title={title} />
      <p className="max-w-[60ch] text-[15px] leading-relaxed text-slate-600">{children}</p>
    </div>
  )
}

// ---------------------------------------------------------------- coloured KPI tile (overview)

const KPI_TONES = {
  teal: { bar: 'bg-[#1f8a80]', icon: 'bg-[#1f8a80] text-white', value: 'text-[#123f3c]', wash: 'from-[#e3f3f1]', meter: 'bg-[#1f8a80]' },
  amber: { bar: 'bg-turmeric-400', icon: 'bg-turmeric-400 text-brand-950', value: 'text-turmeric-700', wash: 'from-turmeric-50', meter: 'bg-turmeric-400' },
  red: { bar: 'bg-seal-500', icon: 'bg-seal-500 text-white', value: 'text-seal-600', wash: 'from-seal-50', meter: 'bg-seal-500' },
  violet: { bar: 'bg-ink-green-500', icon: 'bg-ink-green-500 text-white', value: 'text-ink-green-700', wash: 'from-ink-green-50', meter: 'bg-ink-green-500' },
  ink: { bar: 'bg-brand-800', icon: 'bg-brand-800 text-white', value: 'text-brand-900', wash: 'from-brand-50', meter: 'bg-brand-700' },
} as const

export function KpiTile({
  label, value, hint, to, tone = 'ink', icon, meter,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  to?: string
  tone?: keyof typeof KPI_TONES
  icon?: ReactNode
  /** 0..1, drawn as a thin bar under the value */
  meter?: number | null
}) {
  const s = KPI_TONES[tone]
  const body = (
    <div className={clsx('relative h-full overflow-hidden rounded-[8px] border border-slate-200 bg-gradient-to-br to-white px-4 pt-4 pb-3.5 transition-shadow', s.wash, to && 'group-hover:shadow-[0_10px_24px_-14px_rgba(18,63,60,0.45)]')}>
      <span className={clsx('absolute inset-x-0 top-0 h-[3px]', s.bar)} />
      <div className="flex items-start justify-between gap-2">
        <span className="text-[13px] leading-snug font-semibold text-slate-600">{label}</span>
        {icon && <span className={clsx('flex size-7 shrink-0 items-center justify-center rounded-full', s.icon)}>{icon}</span>}
      </div>
      <div className={clsx('figure mt-1.5 text-[30px] leading-none font-semibold', s.value)}>{value}</div>
      {meter != null && (
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/80 ring-1 ring-slate-200/70">
          <div className={clsx('h-full rounded-full', s.meter)} style={{ width: `${Math.max(2, Math.min(100, meter * 100))}%` }} />
        </div>
      )}
      {hint && <div className="mt-1.5 text-[12.5px] leading-snug text-slate-500">{hint}</div>}
    </div>
  )
  return to ? <Link to={to} className="group block h-full rounded-[8px] focus-visible:outline-2">{body}</Link> : body
}
