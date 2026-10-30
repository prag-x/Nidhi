import { t } from './i18n'
import type { Role, Severity, Status, Verification } from './types'

type Style = { label: string; className: string; dot: string }

const quiet = 'bg-white text-slate-600 ring-slate-300'
const teal = 'bg-brand-50 text-brand-800 ring-brand-200'
const stamp = 'bg-ink-green-50 text-ink-green-700 ring-ink-green-100'
const amber = 'bg-turmeric-50 text-turmeric-700 ring-turmeric-100'
const red = 'bg-seal-50 text-seal-700 ring-seal-100'

export const STATUS: Record<Status, Style> = {
  SUBMITTED: { label: t('Received'), className: quiet, dot: 'bg-slate-400' },
  UNDER_SCRUTINY: { label: t('Under scrutiny'), className: teal, dot: 'bg-brand-600' },
  DISCREPANCY: { label: t('With institution to rectify'), className: red, dot: 'bg-seal-500' },
  ACTIVE: { label: t('Held'), className: stamp, dot: 'bg-ink-green-600' },
  EXPIRING: { label: t('Maturing soon'), className: amber, dot: 'bg-turmeric-500' },
  MATURED: { label: t('Matured'), className: 'bg-seal-600 text-white ring-seal-600', dot: 'bg-white' },
  RENEWED: { label: t('Renewed'), className: quiet, dot: 'bg-ink-green-500' },
  RELEASE_REQUESTED: { label: t('Release in progress'), className: 'bg-buff-100 text-buff-700 ring-buff-200', dot: 'bg-buff-700' },
  RELEASED: { label: t('Released'), className: quiet, dot: 'bg-slate-400' },
  REJECTED: { label: t('Not accepted'), className: quiet, dot: 'bg-seal-500' },
}

export const STATUS_HEX: Record<Status, string> = {
  SUBMITTED: '#8a9693',
  UNDER_SCRUTINY: '#1f5f5a',
  DISCREPANCY: '#b8322a',
  ACTIVE: '#58408f',
  EXPIRING: '#c98a0c',
  MATURED: '#9e2620',
  RENEWED: '#bfc9c6',
  RELEASE_REQUESTED: '#6b5523',
  RELEASED: '#d8dfdd',
  REJECTED: '#64716e',
}

export const VERIFICATION: Record<Verification, Style> = {
  UNVERIFIED: { label: t('Not verified'), className: quiet, dot: 'bg-slate-300' },
  REQUESTED: { label: t('Awaiting bank'), className: amber, dot: 'bg-turmeric-500' },
  CONFIRMED: { label: t('Bank confirmed'), className: stamp, dot: 'bg-ink-green-600' },
  MISMATCH: { label: t('Bank reply differs'), className: red, dot: 'bg-seal-500' },
  NOT_FOUND: { label: t('Bank has no record'), className: 'bg-seal-600 text-white ring-seal-600', dot: 'bg-white' },
}

export const SEVERITY: Record<Severity, Style> = {
  CRITICAL: { label: t('Critical'), className: 'bg-seal-600 text-white ring-seal-600', dot: 'bg-seal-600' },
  HIGH: { label: t('High'), className: red, dot: 'bg-seal-500' },
  MEDIUM: { label: t('Medium'), className: amber, dot: 'bg-turmeric-500' },
  LOW: { label: t('Low'), className: quiet, dot: 'bg-slate-400' },
  INFO: { label: t('Info'), className: quiet, dot: 'bg-slate-300' },
}

export const ROLE: Record<Role, string> = {
  ADMIN: t('Administrator'),
  COMPETENT_AUTHORITY: t('Competent authority'),
  RB_HEAD: t('Head, Regulation Bureau'),
  RB_OFFICER: t('Dealing officer'),
  ACCOUNTS: t('Finance & Accounts'),
  REGIONAL_OFFICER: t('Regional Office'),
  AUDITOR: t('Audit / vigilance'),
  INSTITUTION: t('Institution'),
}

export const PURPOSE: Record<string, string> = {
  NEW_INSTITUTION: t('New institution'),
  NEW_PROGRAMME: t('New programme'),
  INTAKE_INCREASE: t('Increase in intake'),
  OTHER: t('Other'),
}

export const ALERT_KIND: Record<string, string> = {
  MATURITY_DUE: t('Maturing'),
  MATURED_UNRENEWED: t('Matured, not renewed'),
  VERIFICATION_PENDING: t('Bank reply awaited'),
  DISCREPANCY: t('Discrepancy'),
  FRAUD_SIGNAL: t('Fraud signal'),
  RELEASE_PENDING: t('Release'),
  ESCALATION: t('Escalation'),
  RENEWAL_RISK: t('Likely late'),
  INTEGRITY: t('Integrity'),
}

export const LETTER_KIND: Record<string, string> = {
  ACKNOWLEDGEMENT: t('Acknowledgement'),
  BANK_VERIFICATION: t('Verification request to bank'),
  RECTIFICATION: t('Rectification notice'),
  LIEN_RELEASE: t('Lien release to bank'),
}

export const RELEASE_STEPS = [
  { key: 'REQUESTED', label: t('Requested') },
  { key: 'RECOMMENDED', label: t('Recommended by RB') },
  { key: 'APPROVED', label: t('Approved by competent authority') },
  { key: 'EXECUTED', label: t('Lien released by Accounts') },
] as const
