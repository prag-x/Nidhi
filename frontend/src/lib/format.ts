import { isHindi, t } from './i18n'

const TZ = 'Asia/Kolkata'

const LOCALE = isHindi ? 'hi-IN' : 'en-IN'
const dateFmt = new Intl.DateTimeFormat(LOCALE, { day: '2-digit', month: 'short', year: 'numeric', timeZone: TZ })
const dateOnlyFmt = new Intl.DateTimeFormat(LOCALE, { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' })
const dateTimeFmt = new Intl.DateTimeFormat(LOCALE, {
  day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true, timeZone: TZ,
})
const timeFmt = new Intl.DateTimeFormat(LOCALE, { hour: '2-digit', minute: '2-digit', hour12: true, timeZone: TZ })
const numberFmt = new Intl.NumberFormat('en-IN')

/** Dates without a time ("2026-10-24") are calendar dates; never shift them by timezone. */
function parse(value: string): { date: Date; dateOnly: boolean } {
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value)
  return { date: new Date(dateOnly ? `${value}T00:00:00Z` : value), dateOnly }
}

export function fmtDate(value: string | null | undefined): string {
  if (!value) return '—'
  const { date, dateOnly } = parse(value)
  return (dateOnly ? dateOnlyFmt : dateFmt).format(date)
}

export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return dateTimeFmt.format(new Date(value))
}

export function fmtTime(value: string): string {
  return timeFmt.format(new Date(value))
}

export function fmtNumber(n: number | null | undefined): string {
  return n === null || n === undefined ? '—' : numberFmt.format(n)
}

export function fmtPct(n: number | null | undefined, digits = 1): string {
  return n === null || n === undefined ? '—' : `${n.toFixed(digits)}%`
}

export function timeAgo(value: string | null | undefined): string {
  if (!value) return '—'
  const { date } = parse(value)
  const secs = Math.round((Date.now() - date.getTime()) / 1000)
  if (secs < 45) return t('just now')
  const mins = Math.round(secs / 60)
  if (mins < 60) return t('{n} min ago', { n: mins })
  const hours = Math.round(mins / 60)
  if (hours < 24) return t('{n} h ago', { n: hours })
  const days = Math.round(hours / 24)
  if (days < 31) return days === 1 ? t('1 day ago') : t('{n} days ago', { n: days })
  const months = Math.round(days / 30)
  if (months < 12) return months === 1 ? t('1 month ago') : t('{n} months ago', { n: months })
  return t('{n} years ago', { n: (days / 365).toFixed(1) })
}

export function todayIso(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: TZ }).format(new Date())
}

export function isoDaysAgo(days: number): string {
  const d = new Date(`${todayIso()}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() - days)
  return d.toISOString().slice(0, 10)
}

/** First day of the month `months` months before the current one (whole-month periods for trends). */
export function isoMonthStart(months: number): string {
  const d = new Date(`${todayIso().slice(0, 7)}-01T00:00:00Z`)
  d.setUTCMonth(d.getUTCMonth() - months)
  return d.toISOString().slice(0, 10)
}

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function greeting(): string {
  const hour = Number(new Intl.DateTimeFormat('en-IN', { hour: 'numeric', hour12: false, timeZone: TZ }).format(new Date()))
  if (hour < 12) return t('Good morning')
  if (hour < 17) return t('Good afternoon')
  return t('Good evening')
}

export function plural(n: number, word: string, pluralWord = `${word}s`): string {
  return `${fmtNumber(n)} ${n === 1 ? word : pluralWord}`
}

/** Indian digit grouping: 15,00,000. */
export function fmtINR(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return '₹' + new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(n)
}

/** Compact rupees in lakh / crore, the way the Regulation Bureau writes them. */
export function fmtLakh(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  if (Math.abs(n) >= 1e7) return `₹${(n / 1e7).toLocaleString('en-IN', { maximumFractionDigits: 2 })} cr`
  return `₹${(n / 1e5).toLocaleString('en-IN', { maximumFractionDigits: 2 })} lakh`
}

export function daysLabel(d: number): string {
  if (d === 0) return 'today'
  return d > 0 ? `in ${d} days` : `${-d} days ago`
}
