"""Integrity and evidence: renewal model, ledger verification, measured accuracy, problem context."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..db import get_db
from ..deps import get_current_user, require_roles
from ..enums import HELD_STATUSES, Role, Status
from ..models import (
    AppSetting,
    AuditLog,
    Bank,
    BankRecord,
    Discrepancy,
    Document,
    Institution,
    Instrument,
    InstrumentEvent,
    LedgerAnchor,
    LedgerHead,
    Letter,
    Region,
    User,
)
from ..services import evaluation, prediction
from ..services.audit import audit
from ..services.ledger import anchor, verify_ledger
from .instruments import scoped
from .serializers import instrument_item

router = APIRouter(prefix="/intelligence", tags=["intelligence"])
OVERSIGHT = (Role.ADMIN, Role.COMPETENT_AUTHORITY, Role.RB_HEAD, Role.AUDITOR)
PS = "Smart India Hackathon 2026, Problem Statement 26265 (AICTE, Ministry of Education)"

# What the problem statement says, quoted. The demonstration never borrows real figures.
CONTEXT = {
    "quotes": [
        {"text": "When these activities are managed through fragmented records, manual correspondence or multiple "
                 "tracking mechanisms, it may become difficult to maintain an accurate and up-to-date view of deposit "
                 "status, pending actions and time-sensitive requirements.", "source": PS},
        {"text": "The system should distinguish between information submitted by an institution and information "
                 "independently confirmed by an authorized bank or financial source.", "source": PS},
        {"text": "The prototype should demonstrate measurable improvements in record accuracy, verification turnaround "
                 "time, timely renewal monitoring, reduction in manual tracking effort and visibility into pending "
                 "cases.", "source": PS},
    ],
    "disclaimer": "All institutions, banks, people and deposits in this demonstration are synthetic. Deposit amounts "
                  "and tenures are demonstration values an administrator can change; they are not AICTE's norms.",
}


@router.get("/context")
def context(_: User = Depends(get_current_user)):
    return CONTEXT


# ---------------------------------------------------------------- late-renewal model


@router.get("/renewal-model")
def renewal_model(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return prediction.metrics(db)


@router.post("/renewal-model/retrain")
def retrain(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.ADMIN))):
    m = prediction.train(db)
    prediction.score_held(db)
    audit(db, user, "model_retrained", None, None, request, auc=m.get("auc"))
    db.commit()
    return m


@router.get("/renewal-watch")
def renewal_watch(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """Held instruments with no replacement yet, most likely to be renewed late first."""
    succ = select(Instrument.replaces_id).where(Instrument.replaces_id.is_not(None), Instrument.status != Status.REJECTED)
    q = scoped(user, select(Instrument)).where(Instrument.status.in_(HELD_STATUSES), Instrument.renewal_risk.is_not(None),
                                               Instrument.id.not_in(succ))
    rows = db.scalars(q.options(selectinload(Instrument.institution), selectinload(Instrument.bank),
                                selectinload(Instrument.assigned_officer))
                      .order_by(Instrument.renewal_risk.desc()).limit(limit)).all()
    return [instrument_item(x) | {"renewal_drivers": x.renewal_drivers or []} for x in rows]


# ---------------------------------------------------------------- ledger


@router.get("/ledger/verify")
def ledger_verify(db: Session = Depends(get_db), _: User = Depends(require_roles(*OVERSIGHT))):
    return verify_ledger(db)


class AnchorIn(BaseModel):
    note: str | None = None


@router.post("/ledger/anchor")
def ledger_anchor(body: AnchorIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.ADMIN, Role.AUDITOR))):
    a = anchor(db, note=body.note or f"Checkpoint published by {user.full_name}", user=user)
    if a is None:
        raise HTTPException(409, "The ledger is empty")
    audit(db, user, "ledger_checkpoint", "ledger", a.seq, request, hash=a.hash)
    db.commit()
    return {"seq": a.seq, "hash": a.hash, "at": a.at, "note": a.note}


@router.get("/ledger/entries")
def ledger_entries(page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=200), action: str | None = None,
                   db: Session = Depends(get_db), _: User = Depends(require_roles(*OVERSIGHT))):
    q = select(AuditLog).where(AuditLog.seq.is_not(None))
    if action:
        q = q.where(AuditLog.action == action)
    rows = db.scalars(q.options(selectinload(AuditLog.user)).order_by(AuditLog.seq.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return [{"seq": r.seq, "at": r.at, "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id,
             "user": r.user.full_name if r.user else "System", "hash": r.hash, "prev_hash": r.prev_hash} for r in rows]


@router.get("/ledger/anchors")
def ledger_anchors(db: Session = Depends(get_db), _: User = Depends(require_roles(*OVERSIGHT))):
    rows = db.scalars(select(LedgerAnchor).options(selectinload(LedgerAnchor.created_by))
                      .order_by(LedgerAnchor.id.desc()).limit(50)).all()
    return [{"seq": a.seq, "hash": a.hash, "at": a.at, "note": a.note,
             "by": a.created_by.full_name if a.created_by else "System"} for a in rows]


# ---------------------------------------------------------------- tamper demonstration (demo mode only)

TAMPER_KEY = "demo_tamper_backup"


class TamperIn(BaseModel):
    target: str = "instrument_event"  # instrument_event | ledger


@router.post("/ledger/tamper-demo")
def tamper(body: TamperIn, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.ADMIN))):
    """Simulate an insider editing the database directly (bypassing the application), to show detection."""
    if not get_settings().demo_mode:
        raise HTTPException(404, "Not available")
    if db.get(AppSetting, TAMPER_KEY):
        raise HTTPException(409, "A simulated tampering is already in place; restore it first")
    if body.target == "ledger":
        row = db.scalar(select(AuditLog).where(AuditLog.action != "instrument_event", AuditLog.seq.is_not(None))
                        .order_by(AuditLog.seq.desc()).offset(3).limit(1))
        if row is None:
            raise HTTPException(409, "Nothing to tamper with")
        backup = {"table": "audit_logs", "id": row.id, "column": "ip", "value": row.ip, "seq": row.seq}
        db.execute(text("UPDATE audit_logs SET ip = :v WHERE id = :id"), {"v": "10.0.0.66", "id": row.id})
        what = f"Changed the IP address recorded on ledger entry #{row.seq} ({row.action})."
    else:
        ev = db.scalar(select(InstrumentEvent).where(InstrumentEvent.event_type == "BANK_VERIFIED")
                       .order_by(InstrumentEvent.id.desc()).limit(1))
        if ev is None:
            raise HTTPException(409, "Nothing to tamper with")
        ref_no = db.scalar(select(Instrument.ref_no).where(Instrument.id == ev.instrument_id))
        backup = {"table": "instrument_events", "id": ev.id, "column": "remarks", "value": ev.remarks,
                  "instrument_id": ev.instrument_id, "ref_no": ref_no}
        db.execute(text("UPDATE instrument_events SET remarks = :v WHERE id = :id"),
                   {"v": "Bank confirmed every field. Lien noted in favour of the institution.", "id": ev.id})
        what = f"Rewrote the bank-verification record of {ref_no} directly in the database."
    db.add(AppSetting(key=TAMPER_KEY, value=backup))
    db.commit()
    return {"done": what, "hint": "Run Verify integrity to see it detected.", **backup}


@router.post("/ledger/tamper-demo/restore")
def restore(db: Session = Depends(get_db), user: User = Depends(require_roles(Role.ADMIN))):
    row = db.get(AppSetting, TAMPER_KEY)
    if row is None:
        raise HTTPException(409, "No simulated tampering to undo")
    b = row.value
    table = {"audit_logs": AuditLog, "instrument_events": InstrumentEvent}[b["table"]]
    db.execute(update(table).where(table.id == b["id"]).values({b["column"]: b["value"]}))
    db.delete(row)
    db.commit()
    return {"restored": True}


# ---------------------------------------------------------------- proof

# Updated with each release; the suites themselves live in backend/tests and e2e/.
TEST_SUITE = {"backend_tests": 64, "browser_tests": 17, "databases": ["SQLite", "PostgreSQL 16"]}

MODELS = [
    {"name": "Discrepancy checks", "method": "17 rules: amount and validity against the deposit norm, lien, depositor "
     "name, IFSC, scheduled bank, document against declaration, bank against declaration, reused FDRs and documents",
     "runs": "On this server", "data_sent_outside": False},
    {"name": "FDR document reader", "method": "The PDF's text layer where there is one; Tesseract OCR for scanned PDFs and "
     "photos; label patterns for each field in several bank layouts",
     "runs": "On this server", "data_sent_outside": False},
    {"name": "Bank verification connector", "method": "Pluggable: online lookup where the bank offers it (simulated in "
     "the demo), verification letter with QR otherwise", "runs": "On this server", "data_sent_outside": False},
    {"name": "Late-renewal prediction", "method": "Gradient-boosted trees on the institution's renewal history, 60 days "
     "before maturity, tested on institutions it never saw", "runs": "On this server", "data_sent_outside": False},
]


def _count(db: Session, model) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


@router.get("/proof")
def proof(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Everything the system claims, measured: checks, document reader, renewal model, data, ledger and tests."""
    head = db.get(LedgerHead, 1)
    last = db.scalar(select(LedgerAnchor).order_by(LedgerAnchor.id.desc()).limit(1))
    return {
        "evaluation": evaluation.stored(db),
        "model": prediction.metrics(db),
        "data": {
            "institutions": db.scalar(select(func.count(func.distinct(Instrument.institution_id)))) or 0,
            "instruments": _count(db, Instrument), "events": _count(db, InstrumentEvent),
            "documents": _count(db, Document), "letters": _count(db, Letter), "discrepancies": _count(db, Discrepancy),
            "banks": _count(db, Bank), "bank_records": _count(db, BankRecord), "regions": _count(db, Region),
            "all_institutions": _count(db, Institution), "synthetic": True,
        },
        "ledger": {"entries": head.seq if head else 0,
                   "last_checkpoint": {"seq": last.seq, "at": last.at.isoformat(), "hash": last.hash} if last else None},
        "tests": TEST_SUITE,
        "models": MODELS,
        "external_services": [],
    }


@router.post("/proof/evaluate")
def rerun_evaluation(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.ADMIN))):
    result = evaluation.evaluate_and_store(db)
    audit(db, user, "checks_evaluated", None, None, request, precision=result["checks"]["precision"],
          recall=result["checks"]["recall"])
    db.commit()
    return result


@router.get("/proof/verify")
def proof_verify(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Re-compute every seal. Anyone signed in can run it; details of any break are for oversight roles."""
    v = verify_ledger(db)
    return {k: v.get(k) for k in ("valid", "ledger_entries", "instruments_checked", "seconds", "head_seq", "head_hash")}
