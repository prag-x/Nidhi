from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    event,
    JSON,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, UTCDateTime, utcnow
from .enums import DiscrepancyStatus, InstrumentKind, ReleaseStatus, Status, VerificationStatus

# ---------------------------------------------------------------- master data


class Region(Base):
    """An AICTE Regional Office and the states it covers."""

    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(80))
    address: Mapped[str | None] = mapped_column(String(300))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)

    states: Mapped[list[State]] = relationship(back_populates="region", order_by="State.name")


class State(Base):
    __tablename__ = "states"

    code: Mapped[str] = mapped_column(String(4), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"))

    region: Mapped[Region] = relationship(back_populates="states")


class OrgUnit(Base):
    """A Bureau, Finance & Accounts, a Regional Office or the office of the competent authority."""

    __tablename__ = "org_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    unit_type: Mapped[str] = mapped_column(String(24))
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"))
    description: Mapped[str | None] = mapped_column(String(400))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    region: Mapped[Region | None] = relationship()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    designation: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(24))
    org_unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"))
    phone: Mapped[str | None] = mapped_column(String(20))
    # Set for INSTITUTION users: the one institution they act for.
    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institutions.id"))
    password_hash: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    org_unit: Mapped[OrgUnit | None] = relationship()
    institution: Mapped[Institution | None] = relationship(foreign_keys=[institution_id])


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    aicte_pid: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    normalized_name: Mapped[str] = mapped_column(String(255))
    acronym: Mapped[str | None] = mapped_column(String(24))
    inst_type: Mapped[str] = mapped_column(String(60))
    ownership: Mapped[str] = mapped_column(String(60))
    # The society or trust that runs the institution; FDRs are usually in its name.
    society_name: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str] = mapped_column(String(80))
    district: Mapped[str | None] = mapped_column(String(80))
    state_code: Mapped[str] = mapped_column(ForeignKey("states.code"))
    pincode: Mapped[str | None] = mapped_column(String(10))
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    established_year: Mapped[int | None] = mapped_column(Integer)
    approved_intake: Mapped[int | None] = mapped_column(Integer)
    approval_status: Mapped[str] = mapped_column(String(32), default="APPROVED")
    email: Mapped[str | None] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(20))
    website: Mapped[str | None] = mapped_column(String(160))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    state: Mapped[State] = relationship()
    region: Mapped[Region] = relationship()
    aliases: Mapped[list[InstitutionAlias]] = relationship(
        back_populates="institution", cascade="all, delete-orphan"
    )


class InstitutionAlias(Base):
    """Alternate spellings. Confirmed matches are learned here so the matcher improves over time."""

    __tablename__ = "institution_aliases"
    __table_args__ = (UniqueConstraint("institution_id", "normalized", name="uq_alias"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True)
    alias: Mapped[str] = mapped_column(String(300))
    normalized: Mapped[str] = mapped_column(String(300), index=True)
    source: Mapped[str] = mapped_column(String(16), default="LEARNED")  # MASTER | LEARNED | IMPORT
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    institution: Mapped[Institution] = relationship(back_populates="aliases")


# ---------------------------------------------------------------- banks


class Bank(Base):
    """An issuing bank. `verify_channel` says how AICTE can confirm an FDR with it."""

    __tablename__ = "banks"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True)          # IFSC bank code, e.g. SBIN
    name: Mapped[str] = mapped_column(String(160))
    short_name: Mapped[str] = mapped_column(String(40))
    sector: Mapped[str] = mapped_column(String(24))                    # PUBLIC | PRIVATE | COOPERATIVE | SMALL_FINANCE
    verify_channel: Mapped[str] = mapped_column(String(16))            # GATEWAY | LETTER
    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=True)  # only scheduled banks are accepted
    aliases: Mapped[list | None] = mapped_column(JSON)


class BankRecord(Base):
    """What the bank itself holds about an FDR.

    In the demo this table stands in for the banks' systems: the simulated verification gateway answers from it.
    A production deployment replaces the gateway connector with the bank's own verification service.
    """

    __tablename__ = "bank_records"
    __table_args__ = (UniqueConstraint("bank_id", "fdr_number", name="uq_bank_record"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    bank_id: Mapped[int] = mapped_column(ForeignKey("banks.id"), index=True)
    fdr_number: Mapped[str] = mapped_column(String(40), index=True)
    branch: Mapped[str] = mapped_column(String(120))
    ifsc: Mapped[str] = mapped_column(String(11))
    depositor_name: Mapped[str] = mapped_column(String(255))
    amount: Mapped[float] = mapped_column(Float)
    issue_date: Mapped[date] = mapped_column(Date)
    maturity_date: Mapped[date] = mapped_column(Date)
    lien_holder: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(16), default="LIVE")    # LIVE | CLOSED | RENEWED
    auto_renewal: Mapped[bool] = mapped_column(Boolean, default=False)
    closed_on: Mapped[date | None] = mapped_column(Date)

    bank: Mapped[Bank] = relationship()


# ---------------------------------------------------------------- rules


class DepositRule(Base):
    """How much must be deposited and for how long, by purpose and type of institution. Editable master data."""

    __tablename__ = "deposit_rules"
    __table_args__ = (UniqueConstraint("purpose", "inst_type", name="uq_deposit_rule"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    purpose: Mapped[str] = mapped_column(String(24))
    inst_type: Mapped[str] = mapped_column(String(60))                 # "*" for any type
    amount: Mapped[float] = mapped_column(Float)                       # rupees
    min_tenure_months: Mapped[int] = mapped_column(Integer)            # validity required from the issue date
    note: Mapped[str | None] = mapped_column(String(300))


# ---------------------------------------------------------------- instruments


class Instrument(Base):
    """One security deposit or FDR, from submission to release.

    Fields prefixed with nothing are what the institution declared. What the uploaded document says lives in
    `doc_extract`, and what the bank confirmed lives in the latest `Verification`. They are never merged.
    """

    __tablename__ = "instruments"
    __table_args__ = (
        Index("ix_instr_bank_fdr", "bank_id", "fdr_number"),
        Index("ix_instr_status_maturity", "status", "maturity_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ref_no: Mapped[str | None] = mapped_column(String(24), unique=True)       # NDH-2026-000123
    kind: Mapped[str] = mapped_column(String(20), default=InstrumentKind.FDR)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(24))
    approval_year: Mapped[str] = mapped_column(String(9))                    # 2026-27
    application_ref: Mapped[str | None] = mapped_column(String(40))          # AICTE portal application number
    required_amount: Mapped[float | None] = mapped_column(Float)
    required_valid_until: Mapped[date | None] = mapped_column(Date)

    # Declared by the institution
    fdr_number: Mapped[str] = mapped_column(String(40))
    # FDR number normalised for matching (punctuation dropped, OCR look-alikes folded); set automatically.
    fdr_key: Mapped[str | None] = mapped_column(String(40), index=True)
    bank_id: Mapped[int | None] = mapped_column(ForeignKey("banks.id"), index=True)
    bank_name_raw: Mapped[str | None] = mapped_column(String(160))
    branch: Mapped[str | None] = mapped_column(String(120))
    ifsc: Mapped[str | None] = mapped_column(String(11))
    depositor_name: Mapped[str] = mapped_column(String(255))
    amount: Mapped[float] = mapped_column(Float)
    issue_date: Mapped[date] = mapped_column(Date)
    maturity_date: Mapped[date] = mapped_column(Date, index=True)
    lien_holder: Mapped[str | None] = mapped_column(String(160))             # "Member Secretary, AICTE"
    auto_renewal: Mapped[bool] = mapped_column(Boolean, default=False)

    # Read from the uploaded document (field -> value), and how confident the reader was
    doc_extract: Mapped[dict | None] = mapped_column(JSON)
    doc_extract_confidence: Mapped[float | None] = mapped_column(Float)

    status: Mapped[str] = mapped_column(String(24), default=Status.SUBMITTED, index=True)
    verification_status: Mapped[str] = mapped_column(String(16), default=VerificationStatus.UNVERIFIED, index=True)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    assigned_officer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    submitted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    open_discrepancies: Mapped[int] = mapped_column(Integer, default=0)
    max_severity: Mapped[str | None] = mapped_column(String(16))

    # Renewal chain: a successor replaces this instrument
    replaces_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"))

    next_action: Mapped[str | None] = mapped_column(String(300))
    next_action_due: Mapped[date | None] = mapped_column(Date)
    last_action_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_action_summary: Mapped[str | None] = mapped_column(String(300))
    reminders_sent: Mapped[list | None] = mapped_column(JSON)                # reminder offsets already sent
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)

    # Predicted probability that the renewal or replacement arrives after maturity, and why
    renewal_risk: Mapped[float | None] = mapped_column(Float)
    renewal_drivers: Mapped[list | None] = mapped_column(JSON)
    renewed_late: Mapped[bool | None] = mapped_column(Boolean)               # outcome, once known

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    institution: Mapped[Institution] = relationship()
    bank: Mapped[Bank | None] = relationship()
    assigned_officer: Mapped[User | None] = relationship(foreign_keys=[assigned_officer_id])
    submitted_by: Mapped[User | None] = relationship(foreign_keys=[submitted_by_id])
    replaces: Mapped[Instrument | None] = relationship(remote_side=[id], foreign_keys=[replaces_id])
    events: Mapped[list[InstrumentEvent]] = relationship(
        back_populates="instrument", order_by="InstrumentEvent.seq", cascade="all, delete-orphan"
    )
    documents: Mapped[list[Document]] = relationship(back_populates="instrument", cascade="all, delete-orphan")
    verifications: Mapped[list[Verification]] = relationship(
        back_populates="instrument", order_by="Verification.id", cascade="all, delete-orphan"
    )
    discrepancies: Mapped[list[Discrepancy]] = relationship(
        back_populates="instrument", order_by="Discrepancy.id", cascade="all, delete-orphan",
        foreign_keys="Discrepancy.instrument_id",
    )
    releases: Mapped[list[ReleaseRequest]] = relationship(
        back_populates="instrument", order_by="ReleaseRequest.id", cascade="all, delete-orphan"
    )


class InstrumentEvent(Base):
    """Append-only history of an instrument. Each event is hash-chained to the previous one."""

    __tablename__ = "instrument_events"
    __table_args__ = (UniqueConstraint("instrument_id", "seq", name="uq_instrument_event_seq"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    actor_label: Mapped[str | None] = mapped_column(String(120))     # "System", "Bank gateway", institution name
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str | None] = mapped_column(String(24))
    remarks: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column(JSON)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))

    instrument: Mapped[Instrument] = relationship(back_populates="events")
    actor_user: Mapped[User | None] = relationship(foreign_keys=[actor_user_id])
    documents: Mapped[list[Document]] = relationship(back_populates="event")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("instrument_events.id"))
    doc_type: Mapped[str] = mapped_column(String(24), default="FDR_COPY")  # FDR_COPY | BANK_LETTER | OTHER | LETTER
    filename: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(80), unique=True)
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    instrument: Mapped[Instrument] = relationship(back_populates="documents")
    event: Mapped[InstrumentEvent | None] = relationship(back_populates="documents")
    uploaded_by: Mapped[User | None] = relationship()


class Verification(Base):
    """One attempt to confirm an instrument with the issuing bank, and the bank's answer."""

    __tablename__ = "verifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))                  # REQUESTED | CONFIRMED | MISMATCH | NOT_FOUND
    bank_values: Mapped[dict | None] = mapped_column(JSON)           # what the bank said, field by field
    differences: Mapped[list | None] = mapped_column(JSON)           # fields where bank != declared
    reference: Mapped[str | None] = mapped_column(String(80))        # bank's reply reference / letter number
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    instrument: Mapped[Instrument] = relationship(back_populates="verifications")
    requested_by: Mapped[User | None] = relationship()


class Discrepancy(Base):
    """A problem found by the checks or recorded by an officer. Each one names the rule and the evidence."""

    __tablename__ = "discrepancies"

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    field: Mapped[str | None] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(String(400))
    expected: Mapped[str | None] = mapped_column(String(200))
    found: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(16))                  # RULE | DOCUMENT | BANK | OFFICER
    related_instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"))
    status: Mapped[str] = mapped_column(String(16), default=DiscrepancyStatus.OPEN, index=True)
    raised_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolution_note: Mapped[str | None] = mapped_column(String(400))

    instrument: Mapped[Instrument] = relationship(back_populates="discrepancies", foreign_keys=[instrument_id])
    related_instrument: Mapped[Instrument | None] = relationship(foreign_keys=[related_instrument_id])
    resolved_by: Mapped[User | None] = relationship()


class ReleaseRequest(Base):
    """Release, discharge or refund of a deposit: requested, recommended, approved, executed (maker-checker)."""

    __tablename__ = "release_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(24))
    details: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=ReleaseStatus.REQUESTED, index=True)
    checklist: Mapped[dict | None] = mapped_column(JSON)             # condition -> {ok, note, by, at}
    requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    recommended_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    recommended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    executed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    executed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    decision_note: Mapped[str | None] = mapped_column(Text)
    letter_code: Mapped[str | None] = mapped_column(String(24))

    instrument: Mapped[Instrument] = relationship(back_populates="releases")
    requested_by: Mapped[User | None] = relationship(foreign_keys=[requested_by_id])
    recommended_by: Mapped[User | None] = relationship(foreign_keys=[recommended_by_id])
    approved_by: Mapped[User | None] = relationship(foreign_keys=[approved_by_id])
    executed_by: Mapped[User | None] = relationship(foreign_keys=[executed_by_id])


class Letter(Base):
    """A generated letter. Its code and hash let anyone confirm it is genuine at /verify/<code>."""

    __tablename__ = "letters"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True)
    kind: Mapped[str] = mapped_column(String(24))
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    addressee: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64))
    stored_name: Mapped[str] = mapped_column(String(80))
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    issued_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    instrument: Mapped[Instrument] = relationship()
    issued_by: Mapped[User | None] = relationship()


class Notification(Base):
    """Outbox of messages to institutions and officials (e-mail / SMS gateways plug in here)."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(12))
    recipient: Mapped[str] = mapped_column(String(160))
    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institutions.id"), index=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="QUEUED")   # QUEUED | SENT | FAILED
    dedup_key: Mapped[str | None] = mapped_column(String(160), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


# ---------------------------------------------------------------- alerts & audit


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institutions.id"))
    target_unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"), index=True)
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    target_role: Mapped[str | None] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16), index=True)
    dedup_key: Mapped[str] = mapped_column(String(160), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    acknowledged_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    instrument: Mapped[Instrument | None] = relationship()
    target_unit: Mapped[OrgUnit | None] = relationship()


class AlertRead(Base):
    __tablename__ = "alert_reads"

    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditLog(Base):
    """System ledger: every sign-in, decision, export, configuration change and case-history entry.

    Entries form one hash chain (hash = sha256(prev_hash + canonical entry)), so editing, deleting or
    re-ordering anything, including a whole case with its history, is detectable.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    seq: Mapped[int | None] = mapped_column(Integer, unique=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(48), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(48))
    ip: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict | None] = mapped_column(JSON)
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str | None] = mapped_column(String(64))

    user: Mapped[User | None] = relationship()


class LedgerHead(Base):
    """Single row: the latest sequence number and hash of the system ledger (also serves as a write lock)."""

    __tablename__ = "ledger_head"

    id: Mapped[int] = mapped_column(primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    hash: Mapped[str] = mapped_column(String(64))


class LedgerAnchor(Base):
    """A published checkpoint of the ledger head. Printed or e-mailed outside the system, it makes even a
    complete re-computation of the chain by a database administrator detectable."""

    __tablename__ = "ledger_anchors"

    id: Mapped[int] = mapped_column(primary_key=True)
    seq: Mapped[int] = mapped_column(Integer)
    hash: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    note: Mapped[str | None] = mapped_column(String(200))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    created_by: Mapped[User | None] = relationship()


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | int | float | bool | str | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))




def _set_fdr_key(_mapper, _conn, target: Instrument) -> None:
    from .services.checks import _norm_fdr

    target.fdr_key = _norm_fdr(target.fdr_number)


event.listen(Instrument, "before_insert", _set_fdr_key)
event.listen(Instrument, "before_update", _set_fdr_key)
