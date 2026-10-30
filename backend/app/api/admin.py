from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import require_roles
from ..enums import Role
from ..models import AuditLog, DepositRule, Instrument, Notification, User
from ..security import hash_password, password_problems
from ..services.audit import audit
from ..services.ledger import verify_chain
from ..services.settings import all_settings, set_setting
from ..services.sweeps import run_sweep
from .serializers import user_out, user_ref

router = APIRouter(prefix="/admin", tags=["admin"])
admin_only = require_roles(Role.ADMIN)
admin_or_mgmt = require_roles(Role.ADMIN, Role.COMPETENT_AUTHORITY, Role.RB_HEAD, Role.AUDITOR)


# ---------------------------------------------------------------- users


class UserIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    designation: str = Field(min_length=2, max_length=120)
    role: Role
    org_unit_id: int | None = None
    institution_id: int | None = None
    phone: str | None = Field(None, max_length=20)
    password: str = Field(min_length=8, max_length=128)


class UserPatch(BaseModel):
    full_name: str | None = None
    designation: str | None = None
    role: Role | None = None
    org_unit_id: int | None = None
    is_active: bool | None = None
    password: str | None = Field(None, min_length=8, max_length=128)


@router.get("/users")
def users(db: Session = Depends(get_db), _: User = Depends(admin_or_mgmt)):
    return [user_out(u) for u in db.scalars(select(User).options(selectinload(User.org_unit)).order_by(User.full_name))]


@router.post("/users", status_code=201)
def create_user(body: UserIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    if db.scalar(select(User.id).where(func.lower(User.email) == body.email.lower())):
        raise HTTPException(409, "A user with this email already exists")
    if body.role == Role.INSTITUTION and not body.institution_id:
        raise HTTPException(422, "An institution user must be linked to an institution")
    if body.role in (Role.RB_HEAD, Role.RB_OFFICER, Role.ACCOUNTS, Role.REGIONAL_OFFICER) and not body.org_unit_id:
        raise HTTPException(422, "AICTE officials must belong to a Bureau or Regional Office")
    problems = password_problems(body.password)
    if problems:
        raise HTTPException(422, "Password needs " + ", ".join(problems))
    u = User(email=body.email.lower(), full_name=body.full_name, designation=body.designation, role=body.role,
             org_unit_id=body.org_unit_id, institution_id=body.institution_id, phone=body.phone, password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    audit(db, admin, "user_created", "user", u.id, request, email=u.email, role=u.role)
    db.commit()
    db.refresh(u, ["org_unit"])
    return user_out(u)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(admin_only)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "User not found")
    changes = body.model_dump(exclude_unset=True)
    if "password" in changes:
        problems = password_problems(changes["password"])
        if problems:
            raise HTTPException(422, "Password needs " + ", ".join(problems))
        u.password_hash = hash_password(changes.pop("password"))
        changes["password"] = "reset"
    if u.id == admin.id and changes.get("is_active") is False:
        raise HTTPException(422, "You cannot deactivate your own account")
    for key, value in changes.items():
        if key != "password":
            setattr(u, key, value)
    audit(db, admin, "user_updated", "user", u.id, request, changes=list(changes))
    db.commit()
    db.refresh(u, ["org_unit"])
    return user_out(u)


# ---------------------------------------------------------------- deposit norms


class RuleIn(BaseModel):
    purpose: str = Field(min_length=3, max_length=24)
    inst_type: str = Field(min_length=1, max_length=60)
    amount: float = Field(gt=0, le=1e9)
    min_tenure_months: int = Field(ge=1, le=240)
    note: str | None = Field(None, max_length=300)


@router.get("/deposit-rules")
def deposit_rules(db: Session = Depends(get_db), _: User = Depends(admin_or_mgmt)):
    return [{"id": r.id, "purpose": r.purpose, "inst_type": r.inst_type, "amount": r.amount,
             "min_tenure_months": r.min_tenure_months, "note": r.note}
            for r in db.scalars(select(DepositRule).order_by(DepositRule.purpose, DepositRule.inst_type))]


@router.post("/deposit-rules", status_code=201)
def create_rule(body: RuleIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    if db.scalar(select(DepositRule.id).where(DepositRule.purpose == body.purpose,
                                              DepositRule.inst_type == body.inst_type)):
        raise HTTPException(409, "A rule for this purpose and institution type exists; edit it instead")
    rule = DepositRule(**body.model_dump())
    db.add(rule)
    db.flush()
    audit(db, admin, "deposit_rule_created", "deposit_rule", rule.id, request, **body.model_dump())
    db.commit()
    return {"id": rule.id}


@router.patch("/deposit-rules/{rule_id}")
def update_rule(rule_id: int, body: RuleIn, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(admin_only)):
    rule = db.get(DepositRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Rule not found")
    before = {"amount": rule.amount, "min_tenure_months": rule.min_tenure_months}
    rule.amount, rule.min_tenure_months, rule.note = body.amount, body.min_tenure_months, body.note
    audit(db, admin, "deposit_rule_updated", "deposit_rule", rule.id, request, before=before, **body.model_dump())
    db.commit()
    return {"ok": True, "note": "Applies to deposits lodged from now on; held deposits keep the terms they were "
                                "checked against."}


@router.get("/notifications")
def notifications(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                  institution_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(admin_or_mgmt)):
    """The outbox: every email and SMS the portal sent to institutions."""
    q = select(Notification)
    if institution_id:
        q = q.where(Notification.institution_id == institution_id)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(Notification.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "items": [{"id": n.id, "channel": n.channel, "recipient": n.recipient,
                                       "subject": n.subject, "body": n.body, "status": n.status,
                                       "created_at": n.created_at, "instrument_id": n.instrument_id} for n in rows]}


# ---------------------------------------------------------------- rules & operations


class SettingIn(BaseModel):
    value: bool | int | float | str


@router.get("/settings")
def settings(db: Session = Depends(get_db), _: User = Depends(admin_or_mgmt)):
    return all_settings(db)


@router.put("/settings/{key}")
def put_setting(key: str, body: SettingIn, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(admin_only)):
    try:
        set_setting(db, key, body.value, admin)
    except KeyError:
        raise HTTPException(404, "Unknown setting") from None
    except (TypeError, ValueError):
        raise HTTPException(422, "Invalid value") from None
    audit(db, admin, "setting_changed", "setting", key, request, value=body.value)
    db.commit()
    return all_settings(db)


@router.post("/sweep")
def sweep(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_roles(Role.ADMIN, Role.RB_HEAD))):
    stats = run_sweep(db)
    audit(db, admin, "sweep_run", None, None, request, **stats)
    db.commit()
    return stats


@router.get("/audit")
def audit_log(
    action: str | None = None, user_id: int | None = None, entity_type: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db), _: User = Depends(admin_or_mgmt),
):
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action == action)
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.options(selectinload(AuditLog.user)).order_by(AuditLog.at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    actions = [a for (a,) in db.execute(select(AuditLog.action).distinct().order_by(AuditLog.action))]
    return {"total": total, "actions": actions, "items": [
        {"id": r.id, "at": r.at, "user": user_ref(r.user), "action": r.action, "entity_type": r.entity_type,
         "entity_id": r.entity_id, "ip": r.ip, "details": r.details} for r in rows]}


@router.get("/integrity")
def integrity(db: Session = Depends(get_db), _: User = Depends(admin_or_mgmt)):
    """Verify the hash chain of every instrument history."""
    broken = []
    total = 0
    for inst in db.scalars(select(Instrument).options(selectinload(Instrument.events))):
        total += 1
        result = verify_chain(inst)
        if not result["valid"]:
            broken.append({"instrument_id": inst.id, "ref_no": inst.ref_no, "broken_at_seq": result.get("broken_at_seq")})
    return {"instruments_checked": total, "valid": total - len(broken), "broken": broken}
