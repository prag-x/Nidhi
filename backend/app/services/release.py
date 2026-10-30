"""Release, discharge or refund of a deposit.

Requested (institution or officer) -> recommended (dealing officer, after the condition checklist) -> approved
(competent authority, never the recommender) -> executed (Finance & Accounts; the lien-release letter is issued).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..db import today, utcnow
from ..enums import (
    HELD_STATUSES,
    AlertKind,
    EventType,
    LetterKind,
    ReleaseReason,
    ReleaseStatus,
    Severity,
    Status,
)
from ..models import Instrument, ReleaseRequest, User
from .alerts import raise_alert, resolve_alerts
from .instruments import WorkflowError, record_event, successor_of

REASON_LABELS = {
    ReleaseReason.REPLACED: "Replaced by a newer instrument",
    ReleaseReason.CLOSURE: "Closure of institution / programme",
    ReleaseReason.APPROVAL_NOT_GRANTED: "Approval not granted",
    ReleaseReason.PERIOD_COMPLETED: "Prescribed holding period completed",
    ReleaseReason.OTHER: "Other",
}

# Conditions the dealing officer must confirm before recommending. Each is shown with what the portal knows.
CONDITIONS = [
    ("no_liability", "No dues, penalty or liability pending against the institution"),
    ("no_regulatory_matter", "No regulatory action or show-cause pending that the deposit secures"),
    ("approval_position", "Approval position supports release (closure, refusal, replacement or period over)"),
    ("documents_returned", "Original FDR / receipt and institution's request letter on record"),
]


def auto_facts(inst: Instrument, db: Session) -> dict:
    """What the portal can establish by itself, shown beside each condition."""
    succ = successor_of(db, inst)
    return {
        "successor": {"ref_no": succ.ref_no, "status": succ.status} if succ else None,
        "open_discrepancies": inst.open_discrepancies,
        "verification_status": inst.verification_status,
        "matured": inst.status == Status.MATURED,
    }


def condition_facts(inst: Instrument, db: Session) -> dict:
    """For each release condition, what the portal itself can see. The officer still decides and ticks."""
    f = auto_facts(inst, db)
    r = next((r for r in reversed(inst.releases) if r.status == ReleaseStatus.REQUESTED), None)
    reason = r.reason if r else None
    i = inst.institution
    succ = f["successor"]
    if reason == ReleaseReason.REPLACED:
        approval = (True, f"Replacement {succ['ref_no']} is {succ['status'].lower()}.") if succ else \
            (False, "No replacement instrument on record.")
    elif reason == ReleaseReason.PERIOD_COMPLETED:
        approval = (inst.status == Status.MATURED or inst.maturity_date <= today(),
                    f"Matures on {inst.maturity_date:%d %b %Y}.")
    else:
        approval = (None, f"Institution's approval status on record: {i.approval_status.replace('_', ' ').lower()}.")
    docs = [d for d in inst.documents]
    return {
        "no_liability": {"ok": f["open_discrepancies"] == 0,
                         "text": "No open discrepancies on this deposit." if f["open_discrepancies"] == 0
                         else f"{f['open_discrepancies']} discrepancy(ies) still open."},
        "no_regulatory_matter": {"ok": i.approval_status == "APPROVED" or None,
                                 "text": "Approval in force; no action recorded on the portal." if i.approval_status == "APPROVED"
                                 else f"Approval status is {i.approval_status.replace('_', ' ').lower()}; check with the Approval Bureau."},
        "approval_position": {"ok": approval[0], "text": approval[1]},
        "documents_returned": {"ok": bool(docs) or None,
                               "text": f"{len(docs)} document(s) on record." if docs else "No document on record."},
    }


def request(db: Session, inst: Instrument, user: User, reason: str, details: str | None, *, at=None) -> ReleaseRequest:
    if inst.status not in HELD_STATUSES or inst.status == Status.RELEASE_REQUESTED:
        raise WorkflowError("Release can be requested only for an instrument AICTE is holding.")
    if reason == ReleaseReason.REPLACED:
        succ = successor_of(db, inst)
        if succ is None or succ.status not in HELD_STATUSES:
            raise WorkflowError("No accepted replacement is on record yet; lodge and get the new instrument accepted first.")
    r = ReleaseRequest(instrument_id=inst.id, reason=reason, details=details, status=ReleaseStatus.REQUESTED,
                       requested_by_id=user.id, requested_at=at or utcnow(), checklist={})
    db.add(r)
    inst.releases.append(r)
    db.flush()
    record_event(db, inst, EventType.RELEASE_REQUESTED, user, to_status=Status.RELEASE_REQUESTED, at=at,
                 remarks=f"{REASON_LABELS.get(reason, reason)}." + (f" {details}" if details else ""),
                 meta={"release_id": r.id, "reason": reason})
    inst.next_action = "Check release conditions and recommend"
    raise_alert(db, kind=AlertKind.RELEASE_PENDING, severity=Severity.MEDIUM,
                title=f"Release requested: {inst.ref_no}", message=f"{inst.institution.name} asked for release "
                f"({REASON_LABELS.get(reason, reason).lower()}).", dedup_key=f"release:{r.id}:requested",
                instrument_id=inst.id, institution_id=inst.institution_id,
                target_user_id=inst.assigned_officer_id, target_role=None if inst.assigned_officer_id else "RB_HEAD")
    return r


def recommend(db: Session, r: ReleaseRequest, user: User, checklist: dict, note: str | None, *, at=None) -> None:
    if r.status != ReleaseStatus.REQUESTED:
        raise WorkflowError("Only a new release request can be recommended.")
    missing = [label for key, label in CONDITIONS if not (checklist.get(key) or {}).get("ok")]
    if missing:
        raise WorkflowError("Confirm every condition before recommending: " + "; ".join(missing))
    now = at or utcnow()
    r.checklist = {k: {**v, "by": user.full_name, "at": now.isoformat()} for k, v in checklist.items()}
    r.status = ReleaseStatus.RECOMMENDED
    r.recommended_by_id = user.id
    r.recommended_at = now
    r.decision_note = note
    inst = r.instrument
    record_event(db, inst, EventType.RELEASE_RECOMMENDED, user, at=at, remarks=note or "All conditions confirmed.",
                 meta={"release_id": r.id})
    inst.next_action = "Approval of the competent authority"
    resolve_alerts(db, instrument_id=inst.id, kinds=[AlertKind.RELEASE_PENDING])
    raise_alert(db, kind=AlertKind.RELEASE_PENDING, severity=Severity.MEDIUM, title=f"Release to approve: {inst.ref_no}",
                message=f"Recommended by {user.full_name}: {inst.institution.name}, "
                f"{inst.bank.short_name if inst.bank else ''} FDR {inst.fdr_number}.",
                dedup_key=f"release:{r.id}:recommended", instrument_id=inst.id, institution_id=inst.institution_id,
                target_role="COMPETENT_AUTHORITY")


def decide(db: Session, r: ReleaseRequest, user: User, approve: bool, note: str | None, *, at=None) -> None:
    from .permissions import can_approve_release

    if r.status not in (ReleaseStatus.RECOMMENDED,) and not (not approve and r.status == ReleaseStatus.REQUESTED):
        raise WorkflowError("This request is not awaiting a decision.")
    if approve and not can_approve_release(user, r.recommended_by_id):
        raise WorkflowError("The competent authority must approve, and cannot approve a release they recommended.")
    now = at or utcnow()
    inst = r.instrument
    r.decision_note = note or r.decision_note
    resolve_alerts(db, instrument_id=inst.id, kinds=[AlertKind.RELEASE_PENDING])
    if not approve:
        r.status = ReleaseStatus.REJECTED
        from .instruments import held_status
        from .settings import get_setting

        back = held_status(inst, expiring_days=int(get_setting(db, "expiring_window_days")))
        record_event(db, inst, EventType.RELEASE_REJECTED, user, to_status=back, at=at, remarks=note,
                     meta={"release_id": r.id})
        inst.next_action = None
        return
    r.status = ReleaseStatus.APPROVED
    r.approved_by_id = user.id
    r.approved_at = now
    record_event(db, inst, EventType.RELEASE_APPROVED, user, at=at, remarks=note or "Approved.",
                 meta={"release_id": r.id})
    inst.next_action = "Finance & Accounts to discharge the lien"
    raise_alert(db, kind=AlertKind.RELEASE_PENDING, severity=Severity.MEDIUM, title=f"Release to execute: {inst.ref_no}",
                message=f"Approved by {user.full_name}. Issue the lien-release letter to the bank.",
                dedup_key=f"release:{r.id}:approved", instrument_id=inst.id, institution_id=inst.institution_id,
                target_role="ACCOUNTS")


def execute(db: Session, r: ReleaseRequest, user: User, note: str | None, *, at=None) -> None:
    from .letters import issue_letter
    from .notify import notify_institution

    if r.status != ReleaseStatus.APPROVED:
        raise WorkflowError("Only an approved release can be executed.")
    inst = r.instrument
    letter = issue_letter(db, inst, LetterKind.LIEN_RELEASE, user, at=at)
    now = at or utcnow()
    r.status = ReleaseStatus.EXECUTED
    r.executed_by_id = user.id
    r.executed_at = now
    r.letter_code = letter.code
    record_event(db, inst, EventType.RELEASED, user, to_status=Status.RELEASED, at=at,
                 remarks=(note + " " if note else "") + f"Lien-release letter {letter.code} issued to the bank.",
                 meta={"release_id": r.id, "letter": letter.code})
    inst.next_action = None
    resolve_alerts(db, instrument_id=inst.id)
    notify_institution(db, inst, f"Release of {inst.ref_no} completed",
                       f"AICTE has discharged its lien on FDR {inst.fdr_number}. Letter {letter.code} has been sent to "
                       f"the bank.", key=f"released:{inst.id}")
