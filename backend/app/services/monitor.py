"""The daily monitor: validity and maturity tracking, reminders and escalation.

For every instrument AICTE holds it works out whether it is active, expiring or matured, sends the reminders that
are due (to the dealing officer and the institution), and escalates matured instruments that have not been renewed:
first to the RB head, then to the competent authority. It also chases bank verifications that are taking too long.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import local_date, today, utcnow
from ..enums import (
    HELD_STATUSES,
    AlertKind,
    EventType,
    Severity,
    Status,
    VerificationStatus,
)
from ..models import Instrument
from .alerts import raise_alert, resolve_alerts
from .instruments import held_status, record_event, successor_of
from .notify import notify_institution
from .settings import get_setting


def reminder_offsets(db: Session) -> list[int]:
    raw = str(get_setting(db, "reminder_offsets"))
    return sorted({int(x) for x in raw.replace(" ", "").split(",") if x.strip().isdigit()}, reverse=True)


def run_monitor(db: Session, on: date | None = None, *, quiet: bool = False) -> dict:
    """One pass of the monitor. Safe to run repeatedly: reminders and alerts are sent once each."""
    on = on or today()
    expiring_days = int(get_setting(db, "expiring_window_days"))
    grace = int(get_setting(db, "renewal_grace_days"))
    ca_days = int(get_setting(db, "renewal_escalate_ca_days"))
    offsets = reminder_offsets(db)
    stats = {"expiring": 0, "matured": 0, "reminders": 0, "escalated": 0, "verification_chased": 0, "risk_alerts": 0}
    held = db.scalars(select(Instrument).where(Instrument.status.in_(HELD_STATUSES))
                      .options(selectinload(Instrument.institution))).all()
    for inst in held:
        if inst.status == Status.RELEASE_REQUESTED:
            continue
        new_status = held_status(inst, on, expiring_days)
        succ = successor_of(db, inst)
        if new_status != inst.status:
            ev = EventType.MATURED if new_status == Status.MATURED else (
                EventType.EXPIRING if new_status == Status.EXPIRING else EventType.ACCEPTED)
            if ev != EventType.ACCEPTED:
                record_event(db, inst, ev, None, actor_label="Monitor", to_status=new_status,
                             remarks=f"Matures on {inst.maturity_date:%d %b %Y}.")
            else:
                inst.status = new_status
            stats["expiring" if new_status == Status.EXPIRING else "matured"] += new_status != Status.ACTIVE
        days_left = (inst.maturity_date - on).days
        sent = set(inst.reminders_sent or [])
        # Reminders before maturity, only while no replacement has been lodged.
        if succ is None and days_left >= 0:
            due = [o for o in offsets if days_left <= o and o not in sent]
            if due:
                o = min(due)
                sent.update(x for x in offsets if x >= o)
                inst.reminders_sent = sorted(sent, reverse=True)
                stats["reminders"] += 1
                sev = Severity.HIGH if o <= 7 else (Severity.MEDIUM if o <= 30 else Severity.LOW)
                msg = (f"{inst.bank.short_name if inst.bank else ''} FDR {inst.fdr_number} of {inst.institution.name} "
                       f"matures on {inst.maturity_date:%d %b %Y} ({days_left} days). No renewal lodged yet.")
                raise_alert(db, kind=AlertKind.MATURITY_DUE, severity=sev, title=f"Matures in {days_left} days: {inst.ref_no}",
                            message=msg, dedup_key=f"maturity:{inst.id}:{o}", instrument_id=inst.id,
                            institution_id=inst.institution_id, target_user_id=inst.assigned_officer_id,
                            target_role=None if inst.assigned_officer_id else "RB_HEAD")
                raise_alert(db, kind=AlertKind.MATURITY_DUE, severity=sev, title=f"Renew your FDR {inst.fdr_number}",
                            message=f"It matures on {inst.maturity_date:%d %b %Y}. Lodge the renewed or replacement "
                            f"FDR before then.", dedup_key=f"maturity:{inst.id}:{o}:inst", instrument_id=inst.id,
                            institution_id=inst.institution_id, target_role="INSTITUTION")
                notify_institution(db, inst, f"Renewal due: FDR {inst.fdr_number} ({inst.ref_no})",
                                   f"Your FDR lodged with AICTE matures on {inst.maturity_date:%d %b %Y}. Please lodge "
                                   f"the renewed or replacement FDR on the portal before that date.",
                                   key=f"reminder:{inst.id}:{o}", sms=o <= 30)
                if not quiet:
                    record_event(db, inst, EventType.REMINDER_SENT, None, actor_label="Monitor",
                                 remarks=f"{o}-day reminder sent to the institution and the dealing officer.",
                                 meta={"offset": o}, summary=f"{o}-day reminder sent")
        # Matured and still not renewed: escalate.
        if new_status == Status.MATURED and succ is None:
            overdue = -days_left
            raise_alert(db, kind=AlertKind.MATURED_UNRENEWED, severity=Severity.HIGH,
                        title=f"Matured, not renewed: {inst.ref_no}",
                        message=f"{inst.institution.name}'s FDR matured on {inst.maturity_date:%d %b %Y}; "
                        f"no replacement lodged after {overdue} days.", dedup_key=f"matured:{inst.id}",
                        instrument_id=inst.id, institution_id=inst.institution_id,
                        target_user_id=inst.assigned_officer_id)
            level = 2 if overdue >= ca_days else (1 if overdue >= grace else 0)
            if level > inst.escalation_level:
                inst.escalation_level = level
                stats["escalated"] += 1
                to = "COMPETENT_AUTHORITY" if level == 2 else "RB_HEAD"
                raise_alert(db, kind=AlertKind.ESCALATION, severity=Severity.CRITICAL if level == 2 else Severity.HIGH,
                            title=f"Escalated: {inst.ref_no} unrenewed {overdue} days",
                            message=f"{inst.institution.name} ({inst.institution.city}) has not replaced FDR "
                            f"{inst.fdr_number} of {inst.amount:,.0f} rupees that matured on {inst.maturity_date:%d %b %Y}.",
                            dedup_key=f"escalate:{inst.id}:{level}", instrument_id=inst.id,
                            institution_id=inst.institution_id, target_role=to)
                if not quiet:
                    record_event(db, inst, EventType.ESCALATED, None, actor_label="Monitor",
                                 remarks=f"Unrenewed {overdue} days after maturity; escalated to "
                                 f"{'the competent authority' if level == 2 else 'the RB head'}.",
                                 meta={"level": level})
        # Predicted late renewal.
        threshold = float(get_setting(db, "renewal_risk_alert"))
        if succ is None and inst.renewal_risk is not None and inst.renewal_risk >= threshold and 0 <= days_left <= 120:
            if raise_alert(db, kind=AlertKind.RENEWAL_RISK, severity=Severity.MEDIUM,
                           title=f"Likely to renew late: {inst.ref_no}",
                           message=f"{round(inst.renewal_risk * 100)}% chance the replacement arrives after maturity "
                           f"({inst.maturity_date:%d %b %Y}). Follow up early.", dedup_key=f"risk:{inst.id}",
                           instrument_id=inst.id, institution_id=inst.institution_id,
                           target_user_id=inst.assigned_officer_id):
                stats["risk_alerts"] += 1
    # Periodic re-confirmation with banks that have an online service: an FDR can be closed or have its lien
    # removed at the branch after AICTE accepted it. Re-ask the bank about every held FDR at least twice a year.
    if get_setting(db, "gateway_enabled"):
        from .bankgateway import verify_online

        cutoff = utcnow() - timedelta(days=int(get_setting(db, "reconfirm_days")))
        stats["reconfirmed"] = 0
        for inst in held:
            if stats["reconfirmed"] >= 400 or inst.status == Status.RELEASE_REQUESTED:
                continue
            if inst.bank is None or inst.bank.verify_channel != "GATEWAY":
                continue
            last = max((v.responded_at or v.requested_at for v in inst.verifications), default=None)
            if last is None or last < cutoff:
                verify_online(db, inst, None)
                stats["reconfirmed"] += 1
    # Bank verification taking too long.
    sla = int(get_setting(db, "verification_sla_days"))
    waiting = db.scalars(select(Instrument).where(Instrument.verification_status == VerificationStatus.REQUESTED)).all()
    for inst in waiting:
        v = next((x for x in reversed(inst.verifications) if x.status == VerificationStatus.REQUESTED), None)
        if v and (on - local_date(v.requested_at)).days > sla:
            if raise_alert(db, kind=AlertKind.VERIFICATION_PENDING, severity=Severity.MEDIUM,
                           title=f"Bank reply awaited: {inst.ref_no}",
                           message=f"Verification letter sent {(on - local_date(v.requested_at)).days} days ago to "
                           f"{inst.bank.short_name if inst.bank else 'the bank'}. Send a reminder or call the branch.",
                           dedup_key=f"verify:{v.id}", instrument_id=inst.id, institution_id=inst.institution_id,
                           target_user_id=inst.assigned_officer_id):
                stats["verification_chased"] += 1
    # Alerts about instruments that are now closed are no longer actionable.
    for inst in db.scalars(select(Instrument).where(Instrument.status.in_([Status.RENEWED, Status.RELEASED,
                                                                            Status.REJECTED]),
                                                    Instrument.closed_at >= utcnow() - timedelta(days=2))):
        resolve_alerts(db, instrument_id=inst.id)
    return stats
