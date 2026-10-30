export type Role =
  | 'ADMIN'
  | 'COMPETENT_AUTHORITY'
  | 'RB_HEAD'
  | 'RB_OFFICER'
  | 'ACCOUNTS'
  | 'REGIONAL_OFFICER'
  | 'AUDITOR'
  | 'INSTITUTION'

export type Status =
  | 'SUBMITTED'
  | 'UNDER_SCRUTINY'
  | 'DISCREPANCY'
  | 'ACTIVE'
  | 'EXPIRING'
  | 'MATURED'
  | 'RENEWED'
  | 'RELEASE_REQUESTED'
  | 'RELEASED'
  | 'REJECTED'

export type Verification = 'UNVERIFIED' | 'REQUESTED' | 'CONFIRMED' | 'MISMATCH' | 'NOT_FOUND'
export type Severity = 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type Purpose = 'NEW_INSTITUTION' | 'NEW_PROGRAMME' | 'INTAKE_INCREASE' | 'OTHER'

export interface Page<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

export interface UnitRef {
  id: number
  code: string
  name: string
  unit_type: string
}
export interface UserRef {
  id: number
  full_name: string
  designation: string
}
export interface InstitutionRef {
  id: number
  name: string
  aicte_pid: string
  city: string
  state_code: string
  region_id: number
}
export interface User extends UserRef {
  email: string
  role: Role
  phone: string | null
  is_active: boolean
  org_unit: UnitRef | null
  institution: InstitutionRef | null
  last_login_at: string | null
  created_at: string
}
export interface BankRef {
  id: number
  code: string
  name: string
  short_name: string
  verify_channel: 'GATEWAY' | 'LETTER'
  sector: string
  is_scheduled: boolean
}

export interface InstitutionStats {
  held: number
  held_amount: number
  matured_unrenewed: number
  expiring: number
  pending: number
  open_discrepancies: number
  renewals: number
  renewed_late: number
  instruments: number
  max_risk: number | null
}
export interface Institution extends InstitutionRef {
  inst_type: string
  ownership: string
  society_name: string | null
  address: string | null
  district: string | null
  state_name: string
  pincode: string | null
  region: { id: number; code: string; name: string; city: string } | null
  established_year: number | null
  approved_intake: number | null
  approval_status: string
  email: string | null
  phone: string | null
  stats: InstitutionStats | null
}

export interface InstrumentItem {
  id: number
  ref_no: string
  kind: 'FDR' | 'SECURITY_DEPOSIT'
  purpose: Purpose
  approval_year: string
  institution: InstitutionRef
  bank: BankRef | null
  bank_name_raw: string | null
  fdr_number: string
  amount: number
  required_amount: number | null
  issue_date: string
  maturity_date: string
  days_to_maturity: number
  status: Status
  verification_status: Verification
  open_discrepancies: number
  max_severity: Severity | null
  assigned_officer: UserRef | null
  submitted_at: string
  last_action_at: string | null
  last_action_summary: string | null
  next_action: string | null
  renewal_risk: number | null
  replaces_id: number | null
  auto_renewal: boolean
  renewed_late?: boolean | null
  renewal_drivers?: Driver[]
}

export interface Driver {
  factor: string
  impact: number
  text: string
}
export interface DocumentOut {
  id: number
  doc_type: string
  filename: string
  content_type: string
  size_bytes: number
  sha256: string
  uploaded_at: string
  uploaded_by: UserRef | null
}
export interface EventOut {
  id: number
  seq: number
  event_type: string
  label: string
  occurred_at: string
  actor: UserRef | null
  actor_label: string
  from_status: Status | null
  to_status: Status | null
  remarks: string | null
  meta: Record<string, unknown> | null
  hash: string
  prev_hash: string
  documents: DocumentOut[]
}
export interface DiscrepancyOut {
  id: number
  code: string
  title: string
  severity: Severity
  field: string | null
  field_label: string | null
  message: string
  expected: string | null
  found: string | null
  source: string
  status: 'OPEN' | 'RESOLVED' | 'WAIVED'
  raised_at: string
  resolved_at: string | null
  resolved_by: UserRef | null
  resolution_note: string | null
  related: { id: number; ref_no: string; institution: InstitutionRef } | null
}
export interface VerificationOut {
  id: number
  channel: 'GATEWAY' | 'LETTER' | 'MANUAL'
  status: Verification
  bank_values: Record<string, unknown> | null
  differences: { field: string; declared: unknown; bank: unknown }[] | null
  reference: string | null
  requested_at: string
  responded_at: string | null
  requested_by: UserRef | null
}
export interface ReleaseOut {
  id: number
  reason: string
  reason_label: string
  details: string | null
  status: 'REQUESTED' | 'RECOMMENDED' | 'APPROVED' | 'EXECUTED' | 'REJECTED'
  checklist: Record<string, { ok: boolean; note?: string; by?: string; at?: string }>
  requested_by: UserRef | null
  requested_at: string
  recommended_by: UserRef | null
  recommended_at: string | null
  approved_by: UserRef | null
  approved_at: string | null
  executed_by: UserRef | null
  executed_at: string | null
  decision_note: string | null
  letter_code: string | null
}
export interface LetterOut {
  id: number
  code: string
  kind: string
  addressee: string
  subject: string
  sha256: string
  issued_at: string
  issued_by: UserRef | null
  revoked: boolean
}
export interface CompareRow {
  field: string
  label: string
  declared: string | number | null
  document: string | number | null
  bank: string | number | null
  document_agrees: boolean | null
  bank_agrees: boolean | null
}
export interface InstrumentDetail extends InstrumentItem {
  institution: Institution & InstitutionRef
  branch: string | null
  ifsc: string | null
  depositor_name: string
  lien_holder: string | null
  application_ref: string | null
  required_valid_until: string | null
  doc_extract: Record<string, unknown> | null
  doc_extract_confidence: number | null
  verified_at: string | null
  accepted_at: string | null
  closed_at: string | null
  submitted_by: UserRef | null
  escalation_level: number
  renewal_drivers: Driver[]
  renewed_late: boolean | null
  compare: CompareRow[]
  discrepancies: DiscrepancyOut[]
  open_discrepancy_list: DiscrepancyOut[]
  verifications: VerificationOut[]
  documents: DocumentOut[]
  releases: ReleaseOut[]
  events: EventOut[]
  replaces: { id: number; ref_no: string; status: Status; maturity_date: string } | null
  permissions: {
    scrutinise: boolean
    assign: boolean
    waive: boolean
    rectify: boolean
    request_release: boolean
    recommend_release: boolean
    approve_release: boolean
    execute_release: boolean
    renew: boolean
    reverify: boolean
  }
}

export interface AlertItem {
  id: number
  kind: string
  severity: Severity
  title: string
  message: string
  instrument_id: number | null
  institution_id: number | null
  ref_no: string | null
  status: 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED'
  created_at: string
  target_unit: UnitRef | null
  target_role: string | null
  read: boolean
}

export interface Meta {
  regions: { id: number; code: string; name: string; city: string; lat: number; lon: number; states: { code: string; name: string }[] }[]
  units: (UnitRef & { region_id: number | null })[]
  banks: BankRef[]
  officers: (UserRef & { role: Role })[]
  statuses: { value: Status; label: string }[]
  purposes: { value: Purpose; label: string }[]
  kinds: { value: string; label: string }[]
  verification: { value: Verification; label: string }[]
  release_reasons: { value: string; label: string }[]
  release_conditions: { key: string; label: string }[]
  checks: { code: string; title: string; severity: Severity }[]
  alert_kinds: string[]
  deposit_rules: { id: number; purpose: string; inst_type: string; amount: number; min_tenure_months: number; note: string | null }[]
  lien_holder: string
}

export interface ReportOut {
  key: string
  title: string
  subtitle: string
  columns: { key: string; label: string; kind: string }[]
  rows: Record<string, string | number | null>[]
  totals: Record<string, string | number | null> | null
  notes: string[]
}
