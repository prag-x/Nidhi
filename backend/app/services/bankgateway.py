"""Confirming an instrument with the issuing bank.

The portal talks to banks through a connector. The demo uses `SimulatedGateway`, which answers from the
`bank_records` table standing in for the banks' own systems. A real deployment registers a connector per bank (its
verification API, or an intermediary service) with the same `lookup` method; nothing else changes.

Banks without an online service get a verification letter instead, and the officer records the branch's reply.
Either way the bank's answer is stored separately from what the institution declared, field by field.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..enums import EventType, VerificationChannel, VerificationStatus
from ..models import BankRecord, Instrument, User, Verification
from .checks import _norm_fdr, compare_values

COMPARED = ("fdr_number", "amount", "issue_date", "maturity_date", "depositor_name", "lien_holder")


@dataclass
class BankAnswer:
    found: bool
    values: dict | None = None
    reference: str | None = None


class SimulatedGateway:
    """Stand-in for banks' verification services, answering from `bank_records`."""

    name = "Simulated bank verification gateway"

    def lookup(self, db: Session, inst: Instrument) -> BankAnswer:
        key = _norm_fdr(inst.fdr_number)
        rows = db.scalars(select(BankRecord).where(BankRecord.bank_id == inst.bank_id)).all() if inst.bank_id else []
        rec = next((r for r in rows if _norm_fdr(r.fdr_number) == key), None)
        if rec is None:
            return BankAnswer(False, reference=f"GW-{utcnow():%y%m%d%H%M%S}")
        return BankAnswer(True, {
            "fdr_number": rec.fdr_number, "amount": rec.amount, "issue_date": rec.issue_date.isoformat(),
            "maturity_date": rec.maturity_date.isoformat(), "depositor_name": rec.depositor_name,
            "lien_holder": rec.lien_holder, "branch": rec.branch, "ifsc": rec.ifsc, "status": rec.status,
            "closed_on": rec.closed_on.isoformat() if rec.closed_on else None, "auto_renewal": rec.auto_renewal,
        }, reference=f"GW-{rec.id:06d}")


GATEWAY = SimulatedGateway()


def differences(inst: Instrument, bank_values: dict) -> list[dict]:
    out = []
    for f in COMPARED:
        if f == "lien_holder":
            continue  # the lien is judged against the required text by the checks, not against the declaration
        declared = getattr(inst, f)
        if hasattr(declared, "isoformat"):
            declared = declared.isoformat()
        bank = bank_values.get(f)
        if bank is None:
            continue
        if not compare_values(f, declared, bank):
            out.append({"field": f, "declared": declared, "bank": bank})
    return out


def _apply(db: Session, inst: Instrument, v: Verification, answer: BankAnswer, user: User | None, at=None) -> None:
    from . import checks
    from .instruments import record_event

    v.responded_at = at or utcnow()
    v.reference = answer.reference
    if not answer.found:
        v.status = VerificationStatus.NOT_FOUND
        v.bank_values, v.differences = None, []
    else:
        v.bank_values = answer.values
        v.differences = differences(inst, answer.values)
        closed = (answer.values or {}).get("status") == "CLOSED"
        v.status = VerificationStatus.MISMATCH if (v.differences or closed) else VerificationStatus.CONFIRMED
    inst.verification_status = v.status
    if v.status == VerificationStatus.CONFIRMED:
        if inst.verified_at is None:  # first confirmation; later re-confirmations are kept in the verification log
            inst.verified_at = v.responded_at
    label = {VerificationStatus.CONFIRMED: "Bank confirmed every field",
             VerificationStatus.MISMATCH: "Bank's record differs",
             VerificationStatus.NOT_FOUND: "Bank has no such FDR"}[v.status]
    record_event(db, inst, EventType.BANK_VERIFIED, user, at=at,
                 actor_label=None if user else (GATEWAY.name if v.channel == VerificationChannel.GATEWAY else "Bank"),
                 remarks=f"{label} (ref {v.reference}).", summary=label,
                 meta={"verification_id": v.id, "status": v.status, "differences": v.differences})
    checks.run_and_sync(db, inst, at=at)


def verify_online(db: Session, inst: Instrument, user: User | None, *, at=None) -> Verification:
    """Ask the bank's online service and record the answer straight away."""
    from .instruments import record_event

    v = Verification(instrument_id=inst.id, channel=VerificationChannel.GATEWAY, status=VerificationStatus.REQUESTED,
                     requested_at=at or utcnow(), requested_by_id=user.id if user else None)
    db.add(v)
    inst.verifications.append(v)
    db.flush()
    record_event(db, inst, EventType.BANK_VERIFICATION_REQUESTED, user, at=at,
                 remarks=f"Requested through the {GATEWAY.name.lower()}.", meta={"channel": v.channel})
    _apply(db, inst, v, GATEWAY.lookup(db, inst), user=None, at=at)
    return v


def request_by_letter(db: Session, inst: Instrument, user: User, *, at=None) -> Verification:
    """For banks without an online service: issue a verification letter and wait for the branch's reply."""
    from ..enums import LetterKind
    from .instruments import record_event
    from .letters import issue_letter

    v = Verification(instrument_id=inst.id, channel=VerificationChannel.LETTER, status=VerificationStatus.REQUESTED,
                     requested_at=at or utcnow(), requested_by_id=user.id)
    db.add(v)
    inst.verifications.append(v)
    db.flush()
    letter = issue_letter(db, inst, LetterKind.BANK_VERIFICATION, user)
    v.reference = letter.code
    inst.verification_status = VerificationStatus.REQUESTED
    record_event(db, inst, EventType.BANK_VERIFICATION_REQUESTED, user, at=at,
                 remarks=f"Verification letter {letter.code} sent to the branch.",
                 meta={"channel": v.channel, "letter": letter.code})
    return v


def record_reply(db: Session, inst: Instrument, user: User, values: dict | None, reference: str | None,
                 *, at=None) -> Verification:
    """Record what the branch replied (found with these values, or not found)."""
    v = next((x for x in reversed(inst.verifications) if x.status == VerificationStatus.REQUESTED), None)
    if v is None:
        v = Verification(instrument_id=inst.id, channel=VerificationChannel.MANUAL,
                         status=VerificationStatus.REQUESTED, requested_by_id=user.id)
        db.add(v)
        inst.verifications.append(v)
        db.flush()
    answer = BankAnswer(values is not None, values, reference or v.reference)
    _apply(db, inst, v, answer, user, at=at)
    return v


def verify(db: Session, inst: Instrument, user: User, *, at=None) -> Verification:
    """Use the bank's online service when it has one; otherwise send a letter."""
    from .settings import get_setting

    if inst.bank is not None and inst.bank.verify_channel == "GATEWAY" and get_setting(db, "gateway_enabled"):
        return verify_online(db, inst, user, at=at)
    return request_by_letter(db, inst, user, at=at)
