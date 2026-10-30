from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import get_current_user
from ..enums import AlertKind, InstrumentKind, Purpose, ReleaseReason, Role, Status, VerificationStatus
from ..models import Bank, DepositRule, OrgUnit, Region, User
from ..services.checks import RULES
from ..services.instruments import KIND_LABELS, PURPOSE_LABELS, STATUS_LABELS
from ..services.release import CONDITIONS, REASON_LABELS
from ..services.settings import get_setting
from .serializers import bank_ref, unit_ref, user_ref

router = APIRouter(prefix="/meta", tags=["meta"])

VERIFICATION_LABELS = {
    VerificationStatus.UNVERIFIED: "Not yet verified", VerificationStatus.REQUESTED: "Awaiting bank",
    VerificationStatus.CONFIRMED: "Confirmed by bank", VerificationStatus.MISMATCH: "Bank reply differs",
    VerificationStatus.NOT_FOUND: "Bank has no record",
}


@router.get("")
def meta(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    regions = db.scalars(select(Region).options(selectinload(Region.states)).order_by(Region.name)).all()
    units = db.scalars(select(OrgUnit).where(OrgUnit.is_active.is_(True)).order_by(OrgUnit.unit_type, OrgUnit.code)).all()
    officers = db.scalars(select(User).where(User.is_active.is_(True), User.role.in_([Role.RB_OFFICER, Role.RB_HEAD]))
                          .order_by(User.full_name)).all()
    return {
        "regions": [{"id": r.id, "code": r.code, "name": r.name, "city": r.city, "lat": r.lat, "lon": r.lon,
                     "states": [{"code": s.code, "name": s.name} for s in r.states]} for r in regions],
        "units": [{**unit_ref(u), "region_id": u.region_id} for u in units],
        "banks": [bank_ref(b) for b in db.scalars(select(Bank).order_by(Bank.name))],
        "officers": [{**user_ref(u), "role": u.role} for u in officers],
        "statuses": [{"value": s.value, "label": STATUS_LABELS[s]} for s in Status],
        "purposes": [{"value": p.value, "label": PURPOSE_LABELS[p]} for p in Purpose],
        "kinds": [{"value": k.value, "label": KIND_LABELS[k]} for k in InstrumentKind],
        "verification": [{"value": v.value, "label": VERIFICATION_LABELS[v]} for v in VerificationStatus],
        "release_reasons": [{"value": r.value, "label": REASON_LABELS[r]} for r in ReleaseReason],
        "release_conditions": [{"key": c[0], "label": c[1]} if isinstance(c, tuple) else c for c in CONDITIONS],
        "checks": [{"code": k, "title": v[0], "severity": v[1]} for k, v in RULES.items()],
        "alert_kinds": [k.value for k in AlertKind],
        "deposit_rules": [{"id": r.id, "purpose": r.purpose, "inst_type": r.inst_type, "amount": r.amount,
                           "min_tenure_months": r.min_tenure_months, "note": r.note}
                          for r in db.scalars(select(DepositRule).order_by(DepositRule.purpose, DepositRule.inst_type))],
        "lien_holder": get_setting(db, "lien_holder_text"),
    }
