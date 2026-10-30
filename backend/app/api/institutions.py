from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db, today
from ..deps import get_current_user
from ..enums import HELD_STATUSES, PENDING_SCRUTINY, Role, Status
from ..matching.institutions import get_index
from ..models import Instrument, Institution, User
from ..services.instruments import applicable_rule
from ..services.settings import get_setting
from .serializers import instrument_item, institution_out

router = APIRouter(prefix="/institutions", tags=["institutions"])


def _stats(db: Session, ids: list[int] | None) -> dict[int, dict]:
    q = select(Instrument)
    if ids is not None:
        q = q.where(Instrument.institution_id.in_(ids))
    items = db.scalars(q).all()
    succ = {x.replaces_id for x in items if x.replaces_id and x.status != Status.REJECTED}
    out: dict[int, dict] = defaultdict(lambda: {"held": 0, "held_amount": 0.0, "matured_unrenewed": 0, "expiring": 0,
                                                "pending": 0, "open_discrepancies": 0, "renewals": 0,
                                                "renewed_late": 0, "instruments": 0, "max_risk": None})
    day = today()
    for x in items:
        s = out[x.institution_id]
        s["instruments"] += 1
        if x.status in HELD_STATUSES:
            s["held"] += 1
            s["held_amount"] += x.amount
            if x.id not in succ:
                if x.status == Status.MATURED:
                    s["matured_unrenewed"] += 1
                elif 0 <= (x.maturity_date - day).days <= 90:
                    s["expiring"] += 1
                if x.renewal_risk is not None:
                    s["max_risk"] = max(s["max_risk"] or 0, x.renewal_risk)
        if x.status in PENDING_SCRUTINY:
            s["pending"] += 1
        s["open_discrepancies"] += x.open_discrepancies if x.status in PENDING_SCRUTINY + HELD_STATUSES else 0
        if x.renewed_late is not None:
            s["renewals"] += 1
            s["renewed_late"] += bool(x.renewed_late)
    return out


def _visible(user: User, query):
    if user.role == Role.INSTITUTION:
        return query.where(Institution.id == (user.institution_id or -1))
    if user.role == Role.REGIONAL_OFFICER:
        return query.where(Institution.region_id == (user.org_unit.region_id if user.org_unit else -1))
    return query


@router.get("")
def list_institutions(
    q: str | None = None,
    region_id: int | None = None,
    state_code: str | None = None,
    inst_type: str | None = None,
    with_deposits: bool = True,
    sort: str = "attention",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = _visible(user, select(Institution).options(selectinload(Institution.region), selectinload(Institution.state)))
    if q:
        term = f"%{q.strip()}%"
        query = query.where(or_(Institution.name.ilike(term), Institution.aicte_pid.ilike(term),
                                Institution.city.ilike(term), Institution.society_name.ilike(term)))
    if region_id:
        query = query.where(Institution.region_id == region_id)
    if state_code:
        query = query.where(Institution.state_code == state_code.upper())
    if inst_type:
        query = query.where(Institution.inst_type == inst_type)
    insts = db.scalars(query).all()
    stats = _stats(db, [i.id for i in insts] if len(insts) < 900 else None)
    if with_deposits:
        insts = [i for i in insts if stats.get(i.id, {}).get("instruments")]
    empty = _stats(db, [])[0]

    def st(i):
        return stats.get(i.id, empty)

    keyed = {
        "attention": lambda i: (-(st(i)["matured_unrenewed"] * 4 + st(i)["open_discrepancies"] * 2 + st(i)["expiring"]),
                                -st(i)["held_amount"], i.name),
        "amount": lambda i: (-st(i)["held_amount"], i.name),
        "late": lambda i: (-st(i)["renewed_late"], i.name),
        "risk": lambda i: (-(st(i)["max_risk"] or 0), i.name),
        "name": lambda i: i.name,
    }
    insts = sorted(insts, key=keyed.get(sort, keyed["attention"]))
    page_items = insts[(page - 1) * page_size: page * page_size]
    return {"total": len(insts), "page": page, "page_size": page_size,
            "items": [institution_out(i, user, st(i)) for i in page_items]}


class MatchIn(BaseModel):
    name: str
    pid: str | None = None
    state_code: str | None = None
    city: str | None = None
    pincode: str | None = None


@router.post("/match")
def match(body: MatchIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Find the institution a name refers to, with the reasons for the match."""
    result = get_index(db).match(body.name, pid=body.pid, state_code=body.state_code, city=body.city,
                                 pincode=body.pincode, auto_threshold=0.92, review_threshold=0.6)
    return result.detail()


@router.get("/{institution_id}")
def profile(institution_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    inst = db.scalar(_visible(user, select(Institution)).where(Institution.id == institution_id)
                     .options(selectinload(Institution.region), selectinload(Institution.state),
                              selectinload(Institution.aliases)))
    if inst is None:
        raise HTTPException(404, "Institution not found")
    items = db.scalars(select(Instrument).where(Instrument.institution_id == inst.id)
                       .options(selectinload(Instrument.bank), selectinload(Instrument.institution),
                                selectinload(Instrument.assigned_officer))
                       .order_by(Instrument.issue_date.desc())).all()
    by_id = {x.id: x for x in items}
    # Chains: each renewal points at the instrument it replaced.
    nxt = {x.replaces_id: x.id for x in items if x.replaces_id}
    roots = [x for x in items if not x.replaces_id or x.replaces_id not in by_id]
    chains = []
    for r in sorted(roots, key=lambda x: x.issue_date):
        chain, cur = [], r
        while cur is not None:
            chain.append(instrument_item(cur) | {"renewed_late": cur.renewed_late})
            cur = by_id.get(nxt.get(cur.id))
        chains.append({"purpose": r.purpose, "approval_year": r.approval_year, "instruments": chain})
    rules = []
    for purpose in ("NEW_INSTITUTION", "NEW_PROGRAMME", "INTAKE_INCREASE"):
        rule = applicable_rule(db, purpose, inst.inst_type)
        if rule:
            rules.append({"purpose": purpose, "amount": rule.amount, "min_tenure_months": rule.min_tenure_months})
    return {
        **institution_out(inst, user, _stats(db, [inst.id]).get(inst.id)),
        "aliases": [{"alias": a.alias, "source": a.source} for a in inst.aliases],
        "instruments": [instrument_item(x) | {"renewed_late": x.renewed_late} for x in items],
        "chains": chains,
        "deposit_rules": rules,
        "lien_holder": get_setting(db, "lien_holder_text"),
    }
