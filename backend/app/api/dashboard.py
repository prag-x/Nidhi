"""Dashboards: the whole portfolio for management, and a work queue for each role."""

from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db, local_date, start_of_day, today
from ..deps import get_current_user
from ..enums import HELD_STATUSES, PENDING_SCRUTINY, AlertKind, AlertStatus, ReleaseStatus, Role, Status
from ..models import Alert, Bank, Institution, Instrument, Region, ReleaseRequest, User, Verification
from ..services.instruments import STATUS_LABELS
from ..services.reports import _median, _pct
from .instruments import scoped
from .serializers import instrument_item, release_out

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
OPTS = (selectinload(Instrument.institution), selectinload(Instrument.bank), selectinload(Instrument.assigned_officer))


def _load(db: Session, user: User, region_id: int | None = None, bank_id: int | None = None) -> list[Instrument]:
    q = scoped(user, select(Instrument)).options(*OPTS)
    if region_id:
        q = q.where(Instrument.institution_id.in_(select(Institution.id).where(Institution.region_id == region_id)))
    if bank_id:
        q = q.where(Instrument.bank_id == bank_id)
    return db.scalars(q).all()


def _succ(items: list[Instrument]) -> set[int]:
    return {x.replaces_id for x in items if x.replaces_id and x.status != Status.REJECTED}


def _month_start(d, add: int = 0):
    y, m = d.year, d.month - 1 + add
    return d.replace(year=y + m // 12, month=m % 12 + 1, day=1)


@router.get("/summary")
def summary(region_id: int | None = None, bank_id: int | None = None, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    day = today()
    items = _load(db, user, region_id, bank_id)
    succ = _succ(items)
    held = [x for x in items if x.status in HELD_STATUSES]
    unrenewed = [x for x in held if x.id not in succ]
    expiring = [x for x in unrenewed if 0 <= (x.maturity_date - day).days <= 90]
    matured = [x for x in unrenewed if x.status == Status.MATURED]
    pending = [x for x in items if x.status in PENDING_SCRUTINY]
    year_ago = day - timedelta(days=365)
    accepted = [x for x in items if x.accepted_at and local_date(x.accepted_at) >= year_ago]
    verified = [x for x in items if x.verified_at and local_date(x.verified_at) >= year_ago]
    renew_closed = [x for x in items if x.renewed_late is not None and x.closed_at and local_date(x.closed_at) >= year_ago]
    on_time = sum(1 for x in renew_closed if not x.renewed_late)
    releases = db.scalars(select(ReleaseRequest).where(ReleaseRequest.instrument_id.in_([x.id for x in items]))
                          .where(ReleaseRequest.status.in_([ReleaseStatus.REQUESTED, ReleaseStatus.RECOMMENDED,
                                                            ReleaseStatus.APPROVED]))).all() if items else []
    fraud = db.scalars(select(Alert.instrument_id).where(Alert.kind == AlertKind.FRAUD_SIGNAL,
                                                         Alert.status != AlertStatus.RESOLVED)).all()
    ids = {x.id for x in items}
    turn: dict[str, list[float]] = {"GATEWAY": [], "LETTER": []}
    for ch, req, resp in db.execute(select(Verification.channel, Verification.requested_at, Verification.responded_at)
                                    .where(Verification.responded_at.is_not(None),
                                           Verification.requested_at >= start_of_day(year_ago),
                                           Verification.instrument_id.in_(ids))):
        if ch in turn:
            turn[ch].append((resp - req).total_seconds() / 86400)
    kpis = {
        "held": len(held), "held_amount": sum(x.amount for x in held),
        "expiring_90": len(expiring), "expiring_amount": sum(x.amount for x in expiring),
        "matured_unrenewed": len(matured), "matured_amount": sum(x.amount for x in matured),
        "pending_scrutiny": len(pending),
        "with_discrepancies": sum(1 for x in items if x.open_discrepancies and x.status in PENDING_SCRUTINY + HELD_STATUSES),
        "fraud_signals": len({i for i in fraud if i in ids}),
        "awaiting_bank": sum(1 for x in items if x.verification_status == "REQUESTED"),
        "releases_in_progress": len(releases),
        "renewed_on_time_pct": _pct(on_time, len(renew_closed)), "renewals_closed": len(renew_closed),
        "median_days_to_accept": _median([(local_date(x.accepted_at) - local_date(x.submitted_at)).days for x in accepted]),
        "median_days_to_verify": _median([(local_date(x.verified_at) - local_date(x.submitted_at)).days for x in verified]),
        "institutions": len({x.institution_id for x in held}),
        "verify_days_online": round(_median(turn["GATEWAY"]), 1) if turn["GATEWAY"] else None,
        "verify_days_letter": round(_median(turn["LETTER"]), 1) if turn["LETTER"] else None,
        "verifications_online": len(turn["GATEWAY"]), "verifications_letter": len(turn["LETTER"]),
        "high_risk": sum(1 for x in unrenewed if (x.renewal_risk or 0) >= 0.7 and 0 <= (x.maturity_date - day).days <= 120),
    }
    # Maturity calendar for the next 12 months.
    start = _month_start(day)
    calendar = []
    for i in range(12):
        m0, m1 = _month_start(start, i), _month_start(start, i + 1)
        due = [x for x in held if m0 <= x.maturity_date < m1]
        calendar.append({"month": m0.isoformat(), "count": len(due), "amount": sum(x.amount for x in due),
                         "renewal_lodged": sum(1 for x in due if x.id in succ),
                         "high_risk": sum(1 for x in due if x.id not in succ and (x.renewal_risk or 0) >= 0.7)})
    # Twelve-month trend.
    trend = defaultdict(lambda: {"lodged": 0, "accepted": 0, "released": 0, "renewed_late": 0})
    t0 = _month_start(day, -11)
    for x in items:
        if local_date(x.submitted_at) >= t0:
            trend[local_date(x.submitted_at).strftime("%Y-%m")]["lodged"] += 1
        if x.accepted_at and local_date(x.accepted_at) >= t0:
            trend[local_date(x.accepted_at).strftime("%Y-%m")]["accepted"] += 1
        if x.status == Status.RELEASED and x.closed_at and local_date(x.closed_at) >= t0:
            trend[local_date(x.closed_at).strftime("%Y-%m")]["released"] += 1
        if x.renewed_late and x.closed_at and local_date(x.closed_at) >= t0:
            trend[local_date(x.closed_at).strftime("%Y-%m")]["renewed_late"] += 1
    months = [_month_start(t0, i).strftime("%Y-%m") for i in range(12)]
    by_status = defaultdict(lambda: [0, 0.0])
    for x in items:
        by_status[x.status][0] += 1
        by_status[x.status][1] += x.amount
    banks = {b.id: b for b in db.scalars(select(Bank))}
    by_bank = defaultdict(lambda: [0, 0.0, 0])
    for x in held:
        k = by_bank[x.bank_id]
        k[0] += 1
        k[1] += x.amount
        k[2] += x.verification_status in ("MISMATCH", "NOT_FOUND")
    regions = {r.id: r for r in db.scalars(select(Region))}
    by_region = defaultdict(lambda: {"held": 0, "amount": 0.0, "expiring": 0, "matured": 0, "pending": 0})
    for x in items:
        r = by_region[x.institution.region_id]
        if x.status in HELD_STATUSES:
            r["held"] += 1
            r["amount"] += x.amount
        if x in expiring:
            r["expiring"] += 1
        if x in matured:
            r["matured"] += 1
        if x.status in PENDING_SCRUTINY:
            r["pending"] += 1
    return {
        "as_of": day, "kpis": kpis, "calendar": calendar,
        "trend": [{"month": m, **trend[m]} for m in months],
        "by_status": [{"status": s.value, "label": STATUS_LABELS[s], "count": by_status[s][0], "amount": by_status[s][1]}
                      for s in Status if by_status[s][0]],
        "by_bank": sorted([{"bank_id": bid, "name": banks[bid].name if bid in banks else "Unknown bank",
                            "short_name": banks[bid].short_name if bid in banks else "—", "count": c, "amount": a,
                            "problems": p} for bid, (c, a, p) in by_bank.items()], key=lambda r: -r["amount"]),
        "by_region": [{"region_id": rid, "name": regions[rid].name, "city": regions[rid].city, **v}
                      for rid, v in sorted(by_region.items(), key=lambda kv: -kv[1]["amount"]) if rid in regions],
        "watch": {
            "matured": [instrument_item(x) for x in sorted(matured, key=lambda x: x.maturity_date)[:8]],
            "expiring": [instrument_item(x) for x in sorted(expiring, key=lambda x: x.maturity_date)[:8]],
            "at_risk": [instrument_item(x) for x in sorted(
                [x for x in unrenewed if (x.renewal_risk or 0) >= 0.7 and 0 <= (x.maturity_date - day).days <= 120],
                key=lambda x: -(x.renewal_risk or 0))[:8]],
        },
    }


def _q(db: Session, *conds, order=Instrument.submitted_at, limit=50) -> list[dict]:
    return [instrument_item(x) for x in db.scalars(select(Instrument).where(*conds).options(*OPTS).order_by(order)
                                                   .limit(limit))]


def _releases(db: Session, status: str, user: User | None = None) -> list[dict]:
    rows = db.scalars(select(ReleaseRequest).where(ReleaseRequest.status == status)
                      .options(selectinload(ReleaseRequest.instrument).selectinload(Instrument.institution),
                               selectinload(ReleaseRequest.instrument).selectinload(Instrument.bank))
                      .order_by(ReleaseRequest.requested_at)).all()
    out = []
    for r in rows:
        if user is not None and r.recommended_by_id == user.id:
            continue
        out.append({**release_out(r), "instrument": instrument_item(r.instrument)})
    return out


@router.get("/my")
def my_work(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """What this person needs to act on now, grouped into queues."""
    day = today()
    soon = day + timedelta(days=90)
    queues: list[dict] = []

    def add(key, title, items, hint=""):
        queues.append({"key": key, "title": title, "hint": hint, "count": len(items), "items": items[:25]})

    if user.role == Role.RB_OFFICER:
        mine = Instrument.assigned_officer_id == user.id
        add("scrutiny", "To scrutinise", _q(db, mine, Instrument.status.in_([Status.SUBMITTED, Status.UNDER_SCRUTINY])),
            "New and renewed FDRs assigned to you")
        add("bank", "Awaiting bank reply", _q(db, mine, Instrument.verification_status == "REQUESTED"),
            "Record the branch's reply when it arrives")
        add("rectification", "With the institution for rectification", _q(db, mine, Instrument.status == Status.DISCREPANCY))
        add("matured", "Matured, not renewed", _q(db, mine, Instrument.status == Status.MATURED,
                                                  order=Instrument.maturity_date))
        add("releases", "Release requests to check", _releases(db, ReleaseStatus.REQUESTED))
    elif user.role == Role.RB_HEAD:
        add("unassigned", "Not assigned to an officer",
            _q(db, Instrument.assigned_officer_id.is_(None), Instrument.status.in_(PENDING_SCRUTINY)))
        add("escalated", "Escalated to you", _q(db, Instrument.escalation_level >= 1, Instrument.status == Status.MATURED,
                                                order=Instrument.maturity_date))
        add("discrepancies", "Open discrepancies",
            _q(db, Instrument.open_discrepancies > 0, Instrument.status.in_(PENDING_SCRUTINY + HELD_STATUSES),
               order=Instrument.submitted_at))
        add("releases", "Release requests to recommend", _releases(db, ReleaseStatus.REQUESTED))
    elif user.role == Role.COMPETENT_AUTHORITY:
        add("approve", "Releases awaiting your approval", _releases(db, ReleaseStatus.RECOMMENDED, user),
            "Recommended by the Regulation Bureau after checking every condition")
        add("escalated", "Unrenewed beyond 45 days", _q(db, Instrument.escalation_level >= 2,
                                                       Instrument.status == Status.MATURED, order=Instrument.maturity_date))
    elif user.role == Role.ACCOUNTS:
        add("execute", "Approved releases to execute", _releases(db, ReleaseStatus.APPROVED),
            "Issue the lien-release letter to the bank")
        add("held_soon", "Maturing in 90 days", _q(db, Instrument.status.in_(HELD_STATUSES),
                                                  Instrument.maturity_date.between(day, soon),
                                                  order=Instrument.maturity_date))
    elif user.role == Role.INSTITUTION:
        mine = Instrument.institution_id == (user.institution_id or -1)
        add("renew", "Renew before maturity", _q(db, mine, Instrument.status.in_([Status.EXPIRING, Status.MATURED]),
                                                order=Instrument.maturity_date),
            "Lodge the renewed or replacement FDR before the date shown")
        add("rectify", "Discrepancies to rectify", _q(db, mine, Instrument.status == Status.DISCREPANCY))
        add("pending", "Under scrutiny at AICTE", _q(db, mine, Instrument.status.in_([Status.SUBMITTED,
                                                                                        Status.UNDER_SCRUTINY])))
        add("held", "Held by AICTE", _q(db, mine, Instrument.status.in_([Status.ACTIVE, Status.RELEASE_REQUESTED]),
                                        order=Instrument.maturity_date))
    else:
        add("matured", "Matured, not renewed", _q(db, Instrument.status == Status.MATURED, order=Instrument.maturity_date))
    return {"role": user.role, "queues": queues}
