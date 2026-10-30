"""Instrument lifecycle: submission, history, assignment, acceptance and renewal.

Every change is written as a sealed event in the instrument's own hash chain and in the system ledger.
"""

from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import local_date, today, utcnow
from ..enums import (
    HELD_STATUSES,
    OPEN_STATUSES,
    PENDING_SCRUTINY,
    DiscrepancyStatus,
    EventType,
    InstrumentKind,
    Role,
    Status,
    VerificationStatus,
)
from ..models import Bank, DepositRule, Instrument, InstrumentEvent, User
from .events import queue_event
from .ledger import GENESIS, ledger_event, seal

STATUS_LABELS = {
    Status.SUBMITTED: "Submitted", Status.UNDER_SCRUTINY: "Under scrutiny", Status.DISCREPANCY: "Discrepancy",
    Status.ACTIVE: "Active", Status.EXPIRING: "Expiring", Status.MATURED: "Matured",
    Status.RENEWED: "Renewed", Status.RELEASE_REQUESTED: "Release requested", Status.RELEASED: "Released",
    Status.REJECTED: "Rejected",
}

EVENT_LABELS = {
    EventType.SUBMITTED: "Submitted", EventType.DOCUMENT_ATTACHED: "Document attached",
    EventType.DOCUMENT_READ: "Document read", EventType.CHECKS_RUN: "Automatic checks",
    EventType.ASSIGNED: "Assigned", EventType.SCRUTINY_STARTED: "Scrutiny started",
    EventType.OBSERVATION: "Observation recorded",
    EventType.BANK_VERIFICATION_REQUESTED: "Bank verification requested",
    EventType.BANK_VERIFIED: "Bank reply recorded", EventType.DISCREPANCY_RAISED: "Discrepancy raised",
    EventType.DISCREPANCY_RESOLVED: "Discrepancy resolved", EventType.DISCREPANCY_WAIVED: "Discrepancy waived",
    EventType.RECTIFICATION_SUBMITTED: "Rectification submitted", EventType.ACCEPTED: "Accepted",
    EventType.REJECTED: "Rejected", EventType.REMINDER_SENT: "Reminder sent", EventType.EXPIRING: "Expiring",
    EventType.MATURED: "Matured", EventType.ESCALATED: "Escalated",
    EventType.RENEWAL_SUBMITTED: "Renewal submitted", EventType.RENEWED: "Renewed",
    EventType.RELEASE_REQUESTED: "Release requested", EventType.RELEASE_RECOMMENDED: "Release recommended",
    EventType.RELEASE_APPROVED: "Release approved", EventType.RELEASE_REJECTED: "Release rejected",
    EventType.RELEASED: "Released", EventType.LETTER_ISSUED: "Letter issued",
    EventType.FIELD_CORRECTED: "Record corrected",
}

PURPOSE_LABELS = {
    "NEW_INSTITUTION": "New institution", "NEW_PROGRAMME": "New programme",
    "INTAKE_INCREASE": "Increase in intake", "OTHER": "Other",
}
KIND_LABELS = {InstrumentKind.FDR: "Fixed Deposit Receipt", InstrumentKind.SECURITY_DEPOSIT: "Security deposit"}


class WorkflowError(Exception):
    """An action that is not allowed in the instrument's current state."""


# ---------------------------------------------------------------- history


def record_event(
    db: Session,
    inst: Instrument,
    event_type: EventType,
    user: User | None = None,
    *,
    remarks: str | None = None,
    meta: dict | None = None,
    to_status: str | None = None,
    actor_label: str | None = None,
    at=None,
    summary: str | None = None,
) -> InstrumentEvent:
    """Append a sealed event; optionally move the instrument to a new status."""
    last = db.scalar(
        select(InstrumentEvent).where(InstrumentEvent.instrument_id == inst.id)
        .order_by(InstrumentEvent.seq.desc()).limit(1)
    ) if inst.id else None
    seq = (last.seq + 1) if last else 1
    prev_hash = last.hash if last else GENESIS
    from_status = inst.status
    if to_status and to_status != inst.status:
        inst.status = to_status
        if to_status in (Status.RENEWED, Status.RELEASED, Status.REJECTED):
            inst.closed_at = at or utcnow()
    label = actor_label
    if label is None and user is not None:
        label = user.institution.name if user.role == Role.INSTITUTION and user.institution else user.full_name
    ev = InstrumentEvent(
        instrument_id=inst.id, seq=seq, event_type=event_type, occurred_at=at or utcnow(),
        actor_user_id=user.id if user else None, actor_label=label or "System",
        from_status=from_status if to_status else None, to_status=to_status, remarks=remarks, meta=meta,
    )
    seal(ev, prev_hash)
    db.add(ev)
    db.flush()
    ledger_event(db, ev)
    inst.last_action_at = ev.occurred_at
    inst.last_action_summary = summary or EVENT_LABELS.get(event_type, event_type)
    queue_event(db, "instrument", {"id": inst.id, "ref_no": inst.ref_no, "event": event_type,
                                    "status": inst.status, "institution_id": inst.institution_id})
    return ev


# ---------------------------------------------------------------- submission


def next_ref_no(db: Session, year: int | None = None) -> str:
    year = year or today().year
    prefix = f"NDH-{year}-"
    last = db.scalar(select(func.max(Instrument.ref_no)).where(Instrument.ref_no.like(f"{prefix}%")))
    n = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{n:06d}"


def applicable_rule(db: Session, purpose: str, inst_type: str) -> DepositRule | None:
    rule = db.scalar(select(DepositRule).where(DepositRule.purpose == purpose, DepositRule.inst_type == inst_type))
    return rule or db.scalar(select(DepositRule).where(DepositRule.purpose == purpose, DepositRule.inst_type == "*"))


def required_terms(db: Session, inst: Instrument) -> None:
    """Fill in how much is required and until when, from the deposit rules."""
    rule = applicable_rule(db, inst.purpose, inst.institution.inst_type)
    if rule is None:
        inst.required_amount, inst.required_valid_until = None, None
        return
    inst.required_amount = rule.amount
    inst.required_valid_until = inst.issue_date + relativedelta(months=rule.min_tenure_months)


def resolve_bank(db: Session, bank_id: int | None, ifsc: str | None, raw: str | None) -> Bank | None:
    if bank_id:
        return db.get(Bank, bank_id)
    if ifsc and len(ifsc) >= 4:
        bank = db.scalar(select(Bank).where(Bank.code == ifsc[:4].upper()))
        if bank:
            return bank
    if raw:
        key = raw.lower().replace(".", "").strip()
        for bank in db.scalars(select(Bank)):
            names = [bank.name.lower(), bank.short_name.lower(), *[a.lower() for a in (bank.aliases or [])]]
            if key in names:
                return bank
    return None


def pick_officer(db: Session, inst: Instrument) -> User | None:
    """Least-loaded active RB dealing officer."""
    load = dict(db.execute(
        select(Instrument.assigned_officer_id, func.count()).where(Instrument.status.in_(PENDING_SCRUTINY))
        .group_by(Instrument.assigned_officer_id)
    ).all())
    officers = db.scalars(select(User).where(User.role == Role.RB_OFFICER, User.is_active.is_(True))
                          .order_by(User.id)).all()
    if not officers:
        return None
    return min(officers, key=lambda u: (load.get(u.id, 0), u.id))


def submit(db: Session, inst: Instrument, user: User | None, *, at=None, assign: bool = True,
           remarks: str | None = None) -> Instrument:
    """Register a new instrument, work out what is required, assign an officer and run the checks."""
    from . import checks

    inst.ref_no = inst.ref_no or next_ref_no(db, (at or utcnow()).year)
    inst.status = Status.SUBMITTED
    inst.verification_status = VerificationStatus.UNVERIFIED
    inst.submitted_by_id = user.id if user else None
    inst.submitted_at = at or utcnow()
    if inst.bank_id is None:
        bank = resolve_bank(db, None, inst.ifsc, inst.bank_name_raw)
        inst.bank_id = bank.id if bank else None
    db.add(inst)
    db.flush()
    db.refresh(inst, ["institution", "bank"])
    required_terms(db, inst)
    event = EventType.RENEWAL_SUBMITTED if inst.replaces_id else EventType.SUBMITTED
    record_event(db, inst, event, user, at=at, remarks=remarks,
                 meta={"amount": inst.amount, "fdr_number": inst.fdr_number,
                       "maturity_date": inst.maturity_date.isoformat(), "replaces": inst.replaces_id})
    if assign:
        officer = pick_officer(db, inst)
        if officer:
            inst.assigned_officer_id = officer.id
            record_event(db, inst, EventType.ASSIGNED, None, actor_label="System", at=at,
                         remarks=f"Assigned to {officer.full_name} by workload.", meta={"officer_id": officer.id})
    checks.run_and_sync(db, inst, at=at)
    inst.next_action = "Scrutiny and bank verification"
    return inst


def start_scrutiny(db: Session, inst: Instrument, user: User) -> None:
    if inst.status != Status.SUBMITTED:
        raise WorkflowError("Scrutiny has already started.")
    if inst.assigned_officer_id is None:
        inst.assigned_officer_id = user.id
    record_event(db, inst, EventType.SCRUTINY_STARTED, user, to_status=Status.UNDER_SCRUTINY)


def held_status(inst: Instrument, on: date | None = None, expiring_days: int = 90) -> str:
    """ACTIVE, EXPIRING or MATURED, from the maturity date."""
    on = on or today()
    if inst.maturity_date < on:
        return Status.MATURED
    if (inst.maturity_date - on).days <= expiring_days:
        return Status.EXPIRING
    return Status.ACTIVE


def accept(db: Session, inst: Instrument, user: User, remarks: str | None = None, *, at=None) -> None:
    """Accept the instrument as valid security. Needs bank confirmation and no open discrepancies."""
    from .settings import get_setting

    if inst.status not in PENDING_SCRUTINY:
        raise WorkflowError("Only an instrument under scrutiny can be accepted.")
    open_ = [d for d in inst.discrepancies if d.status == DiscrepancyStatus.OPEN]
    if open_:
        raise WorkflowError(f"{len(open_)} discrepancy(ies) are still open. Resolve or waive them first.")
    if inst.kind == InstrumentKind.FDR and inst.verification_status != VerificationStatus.CONFIRMED:
        raise WorkflowError("The issuing bank has not confirmed this FDR yet.")
    status = held_status(inst, expiring_days=int(get_setting(db, "expiring_window_days")))
    inst.accepted_at = at or utcnow()
    record_event(db, inst, EventType.ACCEPTED, user, to_status=status, remarks=remarks, at=at,
                 summary="Accepted as security")
    inst.next_action = None
    inst.next_action_due = None
    if inst.replaces_id:
        complete_renewal(db, inst, user, at=at)


def reject(db: Session, inst: Instrument, user: User, remarks: str, *, at=None) -> None:
    if inst.status not in PENDING_SCRUTINY:
        raise WorkflowError("Only an instrument under scrutiny can be rejected.")
    record_event(db, inst, EventType.REJECTED, user, to_status=Status.REJECTED, remarks=remarks, at=at)
    inst.next_action = None


def complete_renewal(db: Session, successor: Instrument, user: User | None, *, at=None) -> None:
    """The successor has been accepted: close the instrument it replaces."""
    old = successor.replaces
    if old is None or old.status not in HELD_STATUSES:
        return
    # Late means the institution lodged the replacement after the old FDR matured (AICTE's own processing time
    # does not count against the institution).
    old.renewed_late = local_date(successor.submitted_at) > old.maturity_date
    record_event(db, old, EventType.RENEWED, user, to_status=Status.RENEWED, at=at,
                 remarks=f"Replaced by {successor.ref_no}.", meta={"successor_id": successor.id})
    from .alerts import resolve_alerts

    resolve_alerts(db, instrument_id=old.id)


def successor_of(db: Session, inst: Instrument) -> Instrument | None:
    return db.scalar(select(Instrument).where(Instrument.replaces_id == inst.id,
                                              Instrument.status != Status.REJECTED)
                     .order_by(Instrument.id.desc()).limit(1))


def is_open(inst: Instrument) -> bool:
    return inst.status in OPEN_STATUSES
