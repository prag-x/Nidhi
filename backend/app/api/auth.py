from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..db import get_db, utcnow
from ..deps import get_current_user
from ..models import User
from ..security import create_access_token, hash_password, login_limiter, password_problems, verify_password
from ..services.audit import audit, client_ip
from .serializers import user_out

router = APIRouter(prefix="/auth", tags=["auth"])

DEMO_PASSWORD = "Demo@2026"


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if not login_limiter.allow(f"{client_ip(request)}:{email}"):
        raise HTTPException(429, "Too many sign-in attempts. Try again in a minute.")
    user = db.scalar(select(User).where(func.lower(User.email) == email).options(selectinload(User.org_unit)))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        audit(db, user, "login_failed", "user", user.id if user else None, request, email=email)
        db.commit()
        raise HTTPException(401, "Incorrect email or password")
    user.last_login_at = utcnow()
    audit(db, user, "login", "user", user.id, request)
    db.commit()
    return {"access_token": create_access_token(user.id, user.role), "token_type": "bearer", "user": user_out(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_out(user)


@router.post("/change-password")
def change_password(
    body: ChangePasswordIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    problems = password_problems(body.new_password)
    if problems:
        raise HTTPException(422, "New password needs " + ", ".join(problems))
    user.password_hash = hash_password(body.new_password)
    audit(db, user, "password_changed", "user", user.id, request)
    db.commit()
    return {"ok": True}


@router.get("/demo-accounts")
def demo_accounts(db: Session = Depends(get_db)):
    """Lists sign-in accounts for evaluators. Disabled unless NIDHI_DEMO_MODE is on."""
    if not get_settings().demo_mode:
        raise HTTPException(404, "Not available")
    picks = {
        "rb.officer1": "Dealing officer: scrutiny, bank verification, discrepancies",
        "rb.head": "Regulation Bureau head: assignment, escalations, waivers, release recommendations",
        "ms": "Member Secretary: approves releases (never the one who recommended)",
        "accounts": "Finance & Accounts: executes approved releases and issues the lien-release letter",
        "kadamb": "Institution user: lodge a renewal, see reminders and discrepancies",
        "udaan": "Institution with a history of late renewals",
        "ro.wro": "Western Regional Office: deposits of institutions in the region",
        "auditor": "Read-only: ledger verification and the full audit trail",
        "admin": "Users, deposit norms, settings and the tamper demonstration",
    }
    users = db.scalars(select(User).options(selectinload(User.org_unit))).all()
    by_handle = {u.email.split("@")[0]: u for u in users}
    return {
        "password": DEMO_PASSWORD,
        "accounts": [
            {"email": u.email, "full_name": u.full_name, "designation": u.designation, "role": u.role,
             "unit": u.org_unit.code if u.org_unit else None, "hint": hint}
            for h, hint in picks.items() if (u := by_handle.get(h))
        ],
    }
