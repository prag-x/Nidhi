import hashlib
import re
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..db import get_db, today
from ..deps import get_current_user
from ..enums import (
    CLOSED_STATUSES,
    HELD_STATUSES,
    OPEN_STATUSES,
    PENDING_SCRUTINY,
    DiscrepancyStatus,
    EventType,
    InstrumentKind,
    LetterKind,
    Purpose,
    ReleaseReason,
    Role,
    Severity,
    Status,
)
from ..models import Bank, Discrepancy, Document, Institution, Instrument, Letter, ReleaseRequest, User
from ..services import bankgateway, checks, instruments as svc, release, vault
from ..services import permissions as P
from ..services.audit import audit
from ..services.fdrdoc import read_fdr
from ..services.instruments import WorkflowError
from ..services.ledger import verify_chain
from ..services.letters import issue_letter, letter_path
from ..services.notify import notify_institution
from ..services.reports import Column, Report, to_csv, to_xlsx
from .serializers import discrepancy_out, instrument_item, instrument_out, release_out

router = APIRouter(prefix="/instruments", tags=["instruments"])
files_router = APIRouter(tags=["instruments"])

LOAD = (selectinload(Instrument.institution), selectinload(Instrument.bank), selectinload(Instrument.assigned_officer))
FULL = (*LOAD, selectinload(Instrument.events), selectinload(Instrument.documents),
        selectinload(Instrument.verifications), selectinload(Instrument.discrepancies),
        selectinload(Instrument.releases), selectinload(Instrument.submitted_by))
DOC_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
SORTS = {"submitted": Instrument.submitted_at, "maturity": Instrument.maturity_date, "amount": Instrument.amount,
         "risk": Instrument.renewal_risk, "updated": Instrument.last_action_at}
STATUS_GROUPS = {"HELD": HELD_STATUSES, "PENDING": PENDING_SCRUTINY, "OPEN": OPEN_STATUSES, "CLOSED": CLOSED_STATUSES}


class Filters(BaseModel):
    q: str | None = None
    status: str | None = None
    kind: str | None = None
    purpose: str | None = None
    bank_id: int | None = Field(None, ge=1)
    region_id: int | None = Field(None, ge=1)
    state_code: str | None = Field(None, max_length=4)
    institution_id: int | None = Field(None, ge=1)
    verification: str | None = None
    discrepancy: Literal["any", "critical", "none"] | None = None
    expiring_days: int | None = Field(None, ge=0, le=3650)
    maturity_from: date | None = None
    maturity_to: date | None = None
    matured_unrenewed: bool | None = None
    min_amount: float | None = Field(None, ge=0)
    max_amount: float | None = Field(None, ge=0)
    assigned: Literal["me", "unassigned"] | None = None
    at_risk: bool | None = None
    sort: str = "submitted"
    order: Literal["asc", "desc"] = "desc"
    page: int = Field(1, ge=1, le=100000)
    page_size: int = Field(25, ge=1, le=200)


def scoped(user: User, q):
    if user.role == Role.INSTITUTION:
        return q.where(Instrument.institution_id == (user.institution_id or -1))
    if user.role == Role.REGIONAL_OFFICER:
        region = user.org_unit.region_id if user.org_unit else -1
        return q.where(Instrument.institution_id.in_(select(Institution.id).where(Institution.region_id == region)))
    return q


def filtered(f: Filters, user: User):
    q = scoped(user, select(Instrument))
    if f.q:
        like = f"%{f.q.strip()}%"
        q = q.where(or_(Instrument.ref_no.ilike(like), Instrument.fdr_number.ilike(like),
                        Instrument.depositor_name.ilike(like),
                        Instrument.institution_id.in_(select(Institution.id).where(
                            or_(Institution.name.ilike(like), Institution.aicte_pid.ilike(like),
                                Institution.city.ilike(like))))))
    if f.status:
        group = STATUS_GROUPS.get(f.status)
        q = q.where(Instrument.status.in_(list(group))) if group else q.where(Instrument.status == f.status)
    if f.kind:
        q = q.where(Instrument.kind == f.kind)
    if f.purpose:
        q = q.where(Instrument.purpose == f.purpose)
    if f.bank_id:
        q = q.where(Instrument.bank_id == f.bank_id)
    if f.region_id or f.state_code:
        sub = select(Institution.id)
        if f.region_id:
            sub = sub.where(Institution.region_id == f.region_id)
        if f.state_code:
            sub = sub.where(Institution.state_code == f.state_code.upper())
        q = q.where(Instrument.institution_id.in_(sub))
    if f.institution_id:
        q = q.where(Instrument.institution_id == f.institution_id)
    if f.verification:
        q = q.where(Instrument.verification_status == f.verification)
    if f.discrepancy == "any":
        q = q.where(Instrument.open_discrepancies > 0)
    elif f.discrepancy == "critical":
        q = q.where(Instrument.max_severity == Severity.CRITICAL)
    elif f.discrepancy == "none":
        q = q.where(Instrument.open_discrepancies == 0)
    if f.expiring_days is not None:
        q = q.where(Instrument.status.in_(list(HELD_STATUSES)),
                    Instrument.maturity_date.between(today(), today() + timedelta(days=f.expiring_days)))
    if f.maturity_from:
        q = q.where(Instrument.maturity_date >= f.maturity_from)
    if f.maturity_to:
        q = q.where(Instrument.maturity_date <= f.maturity_to)
    if f.matured_unrenewed:
        succ = select(Instrument.replaces_id).where(Instrument.replaces_id.is_not(None),
                                                    Instrument.status != Status.REJECTED)
        q = q.where(Instrument.status == Status.MATURED, Instrument.id.not_in(succ))
    if f.min_amount is not None:
        q = q.where(Instrument.amount >= f.min_amount)
    if f.max_amount is not None:
        q = q.where(Instrument.amount <= f.max_amount)
    if f.assigned == "me":
        q = q.where(Instrument.assigned_officer_id == user.id)
    elif f.assigned == "unassigned":
        q = q.where(Instrument.assigned_officer_id.is_(None), Instrument.status.in_(list(PENDING_SCRUTINY)))
    if f.at_risk:
        q = q.where(Instrument.renewal_risk >= 0.7, Instrument.status.in_([Status.ACTIVE, Status.EXPIRING]))
    return q


def page_of(db: Session, q, f: Filters) -> dict:
    total = db.scalar(select(func.count()).select_from(q.order_by(None).subquery()))
    col = SORTS.get(f.sort, Instrument.submitted_at)
    order = col.asc().nulls_last() if f.order == "asc" else col.desc().nulls_last()
    rows = db.scalars(q.options(*LOAD).order_by(order, Instrument.id.desc())
                      .offset((f.page - 1) * f.page_size).limit(f.page_size)).all()
    return {"total": total, "page": f.page, "page_size": f.page_size, "items": [instrument_item(x) for x in rows]}


@router.get("")
def list_instruments(f: Annotated[Filters, Query()], db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    return page_of(db, filtered(f, user), f)


@router.get("/export")
def export(request: Request, f: Annotated[Filters, Query()], format: Literal["xlsx", "csv"] = "xlsx",
           db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(filtered(f, user).options(*LOAD).order_by(Instrument.maturity_date).limit(20000)).all()
    cols = [Column(k, label, kind) for k, label, kind in [
        ("ref_no", "Nidhi ref", "text"), ("institution", "Institution", "text"), ("pid", "AICTE PID", "text"),
        ("bank", "Bank", "text"), ("fdr", "FDR number", "text"), ("amount", "Amount (Rs)", "int"),
        ("issue", "Issued", "text"), ("maturity", "Matures", "text"), ("days", "Days to maturity", "int"),
        ("status", "Status", "text"), ("verification", "Bank verification", "text"),
        ("discrepancies", "Open discrepancies", "int"), ("officer", "Officer", "text")]]
    table = [{
        "ref_no": x.ref_no, "institution": f"{x.institution.name}, {x.institution.city}", "pid": x.institution.aicte_pid,
        "bank": x.bank.name if x.bank else x.bank_name_raw, "fdr": x.fdr_number, "amount": round(x.amount),
        "issue": x.issue_date.isoformat(), "maturity": x.maturity_date.isoformat(),
        "days": (x.maturity_date - today()).days, "status": svc.STATUS_LABELS.get(x.status, x.status),
        "verification": x.verification_status.title(), "discrepancies": x.open_discrepancies,
        "officer": x.assigned_officer.full_name if x.assigned_officer else "",
    } for x in rows]
    report = Report("instruments", "Security deposits and FDRs", f"{len(table)} instruments matching the filters", cols,
                    table)
    audit(db, user, "export_instruments", "instrument", None, request, format=format, count=len(table))
    db.commit()
    if format == "csv":
        return Response(to_csv(report), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="instruments.csv"'})
    return Response(to_xlsx(report, user.full_name),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="instruments.xlsx"'})


def load(db: Session, inst_id: int, user: User, full: bool = True) -> Instrument:
    x = db.scalar(select(Instrument).where(Instrument.id == inst_id).options(*(FULL if full else LOAD))
                  .execution_options(populate_existing=True))
    if x is None or not P.can_view_instrument(user, x):
        raise HTTPException(404, "Instrument not found")
    return x


@router.get("/{inst_id}")
def get_instrument(inst_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return instrument_out(load(db, inst_id, user), user)


@router.get("/{inst_id}/verify")
def verify_history(inst_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return verify_chain(load(db, inst_id, user))


@router.get("/{inst_id}/release-facts")
def release_facts(inst_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    x = load(db, inst_id, user)
    return release.condition_facts(x, db)


# ---------------------------------------------------------------- submission


class SubmitIn(BaseModel):
    institution_id: int | None = Field(None, ge=1)
    kind: Literal["FDR", "SECURITY_DEPOSIT"] = "FDR"
    purpose: Literal["NEW_INSTITUTION", "NEW_PROGRAMME", "INTAKE_INCREASE", "OTHER"]
    approval_year: str = Field(pattern=r"^\d{4}-\d{2}$")
    application_ref: str | None = Field(None, max_length=40)
    fdr_number: str = Field(min_length=3, max_length=40)
    bank_id: int | None = Field(None, ge=1)
    bank_name: str | None = Field(None, max_length=160)
    branch: str | None = Field(None, max_length=120)
    ifsc: str | None = Field(None, max_length=11)
    depositor_name: str = Field(min_length=2, max_length=255)
    amount: float = Field(gt=0, le=1e10)
    issue_date: date
    maturity_date: date
    lien_holder: str | None = Field(None, max_length=160)
    auto_renewal: bool = False
    replaces_id: int | None = Field(None, ge=1)
    document_token: str | None = Field(None, max_length=64)
    remarks: str | None = Field(None, max_length=2000)

    @field_validator("ifsc")
    @classmethod
    def _ifsc(cls, v):
        return v.strip().upper() if v else v

    @field_validator("issue_date", "maturity_date")
    @classmethod
    def _sane(cls, v):
        if v.year < 1990 or v.year > 2100:
            raise ValueError("date out of range")
        return v


def _safe_name(name: str) -> str:
    return re.sub(r'[^A-Za-z0-9._ -]', "_", name)[:120] or "document"


def _staged_path(token: str, ext: str | None = None) -> Path:
    """Where a document read before submission waits. Without `ext`, finds the staged file whatever its type."""
    base = Path(get_settings().upload_dir) / "staged"
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        return base / "missing"
    if ext:
        return base / f"{token}{ext}"
    return next(iter(sorted(base.glob(f"{token}.*"))), base / "missing")


def _store(db: Session, x: Instrument, data: bytes, filename: str, user: User, doc_type: str) -> Document:
    folder = Path(get_settings().upload_dir)
    folder.mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix.lower()
    stored = f"{uuid.uuid4().hex}{ext}"
    vault.write(folder / stored, data)
    doc = Document(instrument_id=x.id, doc_type=doc_type, filename=Path(filename).name[:255], stored_name=stored,
                   content_type=DOC_TYPES.get(ext, "application/octet-stream"), size_bytes=len(data),
                   sha256=hashlib.sha256(data).hexdigest(), uploaded_by_id=user.id)
    db.add(doc)
    x.documents.append(doc)
    db.flush()
    return doc


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in DOC_TYPES:
        raise HTTPException(422, "Upload a PDF, PNG or JPG file")
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"Files must be under {get_settings().max_upload_mb} MB")
    if not data:
        raise HTTPException(422, "The file is empty")
    sig = {".pdf": data.startswith(b"%PDF"), ".png": data.startswith(b"\x89PNG"),
           ".jpg": data.startswith(b"\xff\xd8\xff"), ".jpeg": data.startswith(b"\xff\xd8\xff")}[ext]
    if not sig:
        raise HTTPException(422, f"The file's contents do not match a {ext} file")
    return data, ext


@router.post("/read-document")
async def read_document(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    """Read an FDR copy before submitting: returns what was found, to pre-fill and cross-check the form."""
    data, ext = await _read_upload(file)
    values, confidence = read_fdr(data, ext)
    token = uuid.uuid4().hex
    path = _staged_path(token, ext)
    vault.write(path, data)
    return {"token": token, "filename": file.filename, "values": values, "confidence": confidence,
            "sha256": hashlib.sha256(data).hexdigest()}


@router.post("", status_code=201)
def submit(body: SubmitIn, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    institution_id = user.institution_id if user.role == Role.INSTITUTION else body.institution_id
    if not institution_id:
        raise HTTPException(422, "Choose the institution")
    if not P.can_submit_for(user, institution_id):
        raise HTTPException(403, "You cannot lodge instruments for this institution")
    if db.get(Institution, institution_id) is None:
        raise HTTPException(422, "Unknown institution")
    if body.maturity_date <= body.issue_date:
        raise HTTPException(422, "The maturity date must be after the issue date")
    replaces = None
    if body.replaces_id:
        replaces = db.get(Instrument, body.replaces_id)
        if replaces is None or replaces.institution_id != institution_id or replaces.status not in HELD_STATUSES:
            raise HTTPException(422, "The instrument being renewed must be one AICTE holds for this institution")
    if body.bank_id and db.get(Bank, body.bank_id) is None:
        raise HTTPException(422, "Unknown bank")
    bank = svc.resolve_bank(db, body.bank_id, body.ifsc, body.bank_name)
    x = Instrument(
        kind=body.kind, institution_id=institution_id, purpose=body.purpose, approval_year=body.approval_year,
        application_ref=body.application_ref, fdr_number=body.fdr_number.strip(), bank_id=bank.id if bank else None,
        bank_name_raw=body.bank_name or (bank.name if bank else None), branch=body.branch, ifsc=body.ifsc,
        depositor_name=body.depositor_name.strip(), amount=body.amount, issue_date=body.issue_date,
        maturity_date=body.maturity_date, lien_holder=body.lien_holder, auto_renewal=body.auto_renewal,
        replaces_id=replaces.id if replaces else None,
    )
    db.add(x)
    db.flush()
    if body.document_token:
        path = _staged_path(body.document_token)
        if path.exists():
            data = vault.read(path)
            _store(db, x, data, f"FDR_{x.fdr_number}{path.suffix}", user, "FDR_COPY")
            x.doc_extract, x.doc_extract_confidence = read_fdr(data, path.suffix)
            path.unlink(missing_ok=True)
    svc.submit(db, x, user, remarks=body.remarks)
    ack = issue_letter(db, x, LetterKind.ACKNOWLEDGEMENT, None)
    notify_institution(db, x, f"Received: {x.ref_no}", f"Your {x.kind.replace('_', ' ').lower()} {x.fdr_number} has been "
                       f"received and registered as {x.ref_no}. Acknowledgement {ack.code}.", key=f"ack:{x.id}")
    audit(db, user, "instrument_submitted", "instrument", x.id, request, ref_no=x.ref_no)
    db.commit()
    return instrument_out(load(db, x.id, user), user)


@router.post("/{inst_id}/documents", status_code=201)
async def upload_document(inst_id: int, request: Request, file: UploadFile = File(...),
                          doc_type: str = Form("FDR_COPY"), db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    x = load(db, inst_id, user)
    allowed = P.can_rectify(user, x) or P.can_scrutinise(user, x) or \
        (user.role == Role.INSTITUTION and user.institution_id == x.institution_id)
    if not allowed or x.status in CLOSED_STATUSES:
        raise HTTPException(403, "You cannot add documents to this instrument")
    if doc_type not in ("FDR_COPY", "BANK_LETTER", "OTHER"):
        raise HTTPException(422, "Unknown document type")
    data, ext = await _read_upload(file)
    doc = _store(db, x, data, file.filename or f"document{ext}", user, doc_type)
    meta = {"filename": doc.filename, "sha256": doc.sha256, "doc_type": doc_type}
    ev = svc.record_event(db, x, EventType.DOCUMENT_ATTACHED, user, remarks=f"{doc.filename} attached.", meta=meta)
    doc.event_id = ev.id
    if doc_type == "FDR_COPY":
        x.doc_extract, x.doc_extract_confidence = read_fdr(data, ext)
        svc.record_event(db, x, EventType.DOCUMENT_READ, None, actor_label="Document reader",
                         remarks=f"Read {round((x.doc_extract_confidence or 0) * 100)}% of the fields.",
                         meta={"values": x.doc_extract})
    checks.run_and_sync(db, x, user=user)
    audit(db, user, "document_uploaded", "instrument", x.id, request, sha256=doc.sha256)
    db.commit()
    return instrument_out(load(db, x.id, user), user)


@files_router.get("/releases")
def list_release_requests(status: Literal["open", "REQUESTED", "RECOMMENDED", "APPROVED", "EXECUTED", "REJECTED", "all"] = "open",
                          page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                          db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Release / refund requests and where each one stands."""
    q = select(ReleaseRequest).join(Instrument, Instrument.id == ReleaseRequest.instrument_id)
    q = scoped(user, q)
    if status == "open":
        q = q.where(ReleaseRequest.status.in_(["REQUESTED", "RECOMMENDED", "APPROVED"]))
    elif status != "all":
        q = q.where(ReleaseRequest.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.options(selectinload(ReleaseRequest.instrument).selectinload(Instrument.institution),
                                selectinload(ReleaseRequest.instrument).selectinload(Instrument.bank),
                                selectinload(ReleaseRequest.instrument).selectinload(Instrument.assigned_officer))
                      .order_by(ReleaseRequest.requested_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [{**release_out(r), "instrument": instrument_item(r.instrument)} for r in rows]}


@files_router.get("/documents/{doc_id}")
def download_document(doc_id: int, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    load(db, doc.instrument_id, user, full=False)
    path = Path(get_settings().upload_dir) / doc.stored_name
    if not path.exists():
        raise HTTPException(410, "The stored file is missing")
    data = vault.read(path)
    audit(db, user, "document_downloaded", "document", doc.id, request)
    db.commit()
    return Response(data, media_type=doc.content_type,
                    headers={"Content-Disposition": f'attachment; filename="{_safe_name(doc.filename)}"'})


@files_router.get("/letters/{code}/pdf")
def download_letter(code: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    letter = db.scalar(select(Letter).where(Letter.code == code))
    if letter is None:
        raise HTTPException(404, "Letter not found")
    load(db, letter.instrument_id, user, full=False)
    path = letter_path(letter)
    if not path.exists():
        raise HTTPException(410, "The stored letter is missing")
    data = vault.read(path)
    audit(db, user, "letter_downloaded", "letter", letter.code, request)
    db.commit()
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{letter.code}.pdf"'})


@router.get("/{inst_id}/letters")
def list_letters(inst_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from .serializers import letter_out

    load(db, inst_id, user, full=False)
    return [letter_out(x) for x in db.scalars(select(Letter).where(Letter.instrument_id == inst_id)
                                               .options(selectinload(Letter.issued_by)).order_by(Letter.id))]


# ---------------------------------------------------------------- actions


class ActionIn(BaseModel):
    remarks: str | None = Field(None, max_length=4000)
    officer_id: int | None = Field(None, ge=1)
    discrepancy_id: int | None = Field(None, ge=1)
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] | None = None
    field: str | None = Field(None, max_length=40)
    found: bool | None = None                      # bank reply: True = found with values, False = no record
    bank_values: dict | None = None
    reference: str | None = Field(None, max_length=80)
    corrections: dict | None = None                # institution's rectification of declared fields
    reason: str | None = None
    checklist: dict | None = None
    approve: bool | None = None


EDITABLE = {"fdr_number": str, "amount": float, "issue_date": date, "maturity_date": date, "depositor_name": str,
            "lien_holder": str, "ifsc": str, "branch": str, "auto_renewal": bool}


def _need(cond: bool, msg: str = "You do not have permission for this action") -> None:
    if not cond:
        raise HTTPException(403, msg)


@router.post("/{inst_id}/actions/{action}")
def act(inst_id: int, action: str, body: ActionIn, request: Request, db: Session = Depends(get_db),
        user: User = Depends(get_current_user)):
    x = load(db, inst_id, user)
    try:
        _dispatch(db, x, action, body, user)
    except WorkflowError as e:
        db.rollback()
        raise HTTPException(409, str(e)) from None
    except ValueError as e:
        db.rollback()
        raise HTTPException(422, str(e)) from None
    audit(db, user, f"instrument_{action}", "instrument", x.id, request, ref_no=x.ref_no)
    db.commit()
    return instrument_out(load(db, x.id, user), user)


def _dispatch(db: Session, x: Instrument, action: str, body: ActionIn, user: User) -> None:  # noqa: C901
    pending = x.status in PENDING_SCRUTINY
    if action == "start_scrutiny":
        _need(P.can_scrutinise(user, x))
        svc.start_scrutiny(db, x, user)
    elif action == "assign":
        _need(P.can_assign(user))
        officer = db.get(User, body.officer_id or 0)
        if officer is None or officer.role != Role.RB_OFFICER:
            raise ValueError("Choose a dealing officer of the Regulation Bureau")
        x.assigned_officer_id = officer.id
        svc.record_event(db, x, EventType.ASSIGNED, user, remarks=f"Assigned to {officer.full_name}.",
                         meta={"officer_id": officer.id})
    elif action == "verify":
        _need(P.can_scrutinise(user, x) and pending)
        if x.status == Status.SUBMITTED:
            svc.start_scrutiny(db, x, user)
        bankgateway.verify(db, x, user)
    elif action == "reverify":
        _need(user.role in (Role.RB_OFFICER, Role.RB_HEAD) and x.status in HELD_STATUSES)
        if x.bank is None or x.bank.verify_channel != "GATEWAY":
            bankgateway.request_by_letter(db, x, user)
        else:
            bankgateway.verify_online(db, x, user)
    elif action == "bank_reply":
        _need(P.can_scrutinise(user, x) or (user.role in (Role.RB_OFFICER, Role.RB_HEAD) and x.status in HELD_STATUSES))
        if body.found is None:
            raise ValueError("Say whether the bank found the FDR")
        values = None
        if body.found:
            values = {k: v for k, v in (body.bank_values or {}).items()
                      if k in ("fdr_number", "amount", "issue_date", "maturity_date", "depositor_name", "lien_holder",
                               "branch", "ifsc", "status")}
            if "amount" in values:
                values["amount"] = float(values["amount"])
        bankgateway.record_reply(db, x, user, values, body.reference)
    elif action == "observation":
        _need(P.can_scrutinise(user, x) or user.role in (Role.RB_HEAD, Role.COMPETENT_AUTHORITY))
        if not body.remarks:
            raise ValueError("Write the observation")
        svc.record_event(db, x, EventType.OBSERVATION, user, remarks=body.remarks)
    elif action == "raise_discrepancy":
        _need(P.can_scrutinise(user, x) and pending)
        if not body.remarks:
            raise ValueError("Describe the discrepancy")
        checks.raise_manual(db, x, user, body.remarks, body.field, body.severity or Severity.MEDIUM)
    elif action in ("resolve_discrepancy", "waive_discrepancy"):
        waive = action == "waive_discrepancy"
        _need(P.can_waive(user) if waive else P.can_scrutinise(user, x))
        d = next((d for d in x.discrepancies if d.id == body.discrepancy_id), None)
        if d is None:
            raise ValueError("Unknown discrepancy")
        if not body.remarks or len(body.remarks.strip()) < 10:
            raise ValueError("Record the reason (at least 10 characters)")
        checks.resolve(db, x, d, user, body.remarks.strip(), waive=waive)
    elif action == "send_for_rectification":
        _need(P.can_scrutinise(user, x) and pending)
        if not x.open_discrepancies:
            raise WorkflowError("There are no open discrepancies to send back.")
        from ..services.settings import get_setting

        letter = issue_letter(db, x, LetterKind.RECTIFICATION, user)
        days = int(get_setting(db, "rectification_days"))
        x.next_action = "Institution to rectify"
        x.next_action_due = today() + timedelta(days=days)
        svc.record_event(db, x, EventType.OBSERVATION, user, to_status=Status.DISCREPANCY,
                         remarks=body.remarks or f"Sent to the institution for rectification (letter {letter.code}); "
                         f"{days} days allowed.", summary="Sent for rectification")
        notify_institution(db, x, f"Action needed: {x.ref_no}", f"{x.open_discrepancies} discrepancy(ies) found in FDR "
                           f"{x.fdr_number}. Please rectify on the portal within {days} days. Letter {letter.code}.",
                           key=f"rectify:{x.id}:{letter.code}", sms=True)
        from ..services.alerts import raise_alert
        from ..enums import AlertKind

        raise_alert(db, kind=AlertKind.DISCREPANCY, severity=Severity.HIGH, title=f"Rectify FDR {x.fdr_number}",
                    message=f"{x.open_discrepancies} discrepancy(ies) to fix within {days} days.",
                    dedup_key=f"rectify:{x.id}:{letter.code}", instrument_id=x.id, institution_id=x.institution_id,
                    target_role="INSTITUTION")
    elif action == "rectify":
        _need(P.can_rectify(user, x))
        changes = {}
        for k, v in (body.corrections or {}).items():
            if k not in EDITABLE:
                raise ValueError(f"{k} cannot be changed")
            typ = EDITABLE[k]
            new = date.fromisoformat(v) if typ is date else (bool(v) if typ is bool else (float(v) if typ is float else str(v).strip()))
            old = getattr(x, k)
            if new != old:
                setattr(x, k, new)
                changes[k] = {"from": str(old) if old is not None else None, "to": str(new)}
        if x.maturity_date <= x.issue_date:
            raise ValueError("The maturity date must be after the issue date")
        db.flush()
        svc.required_terms(db, x)
        svc.record_event(db, x, EventType.RECTIFICATION_SUBMITTED, user, to_status=Status.UNDER_SCRUTINY,
                         remarks=body.remarks or "Rectification submitted.", meta={"changes": changes})
        checks.run_and_sync(db, x, user=user)
    elif action == "accept":
        _need(P.can_scrutinise(user, x))
        svc.accept(db, x, user, body.remarks)
        notify_institution(db, x, f"Accepted: {x.ref_no}", f"FDR {x.fdr_number} has been accepted as security.",
                           key=f"accepted:{x.id}")
    elif action == "reject":
        _need(P.can_scrutinise(user, x))
        if not body.remarks or len(body.remarks.strip()) < 10:
            raise ValueError("Record the reason for rejection (at least 10 characters)")
        svc.reject(db, x, user, body.remarks.strip())
    elif action == "release_request":
        _need(P.can_request_release(user, x))
        if body.reason not in {r.value for r in ReleaseReason}:
            raise ValueError("Choose the reason for release")
        release.request(db, x, user, body.reason, body.remarks)
    elif action == "release_recommend":
        _need(P.can_recommend_release(user))
        r = _open_release(x)
        release.recommend(db, r, user, body.checklist or {}, body.remarks)
    elif action == "release_decide":
        _need(user.role == Role.COMPETENT_AUTHORITY)
        r = _open_release(x)
        release.decide(db, r, user, bool(body.approve), body.remarks)
    elif action == "release_execute":
        _need(P.can_execute_release(user))
        r = _open_release(x)
        release.execute(db, r, user, body.remarks)
    else:
        raise HTTPException(404, "Unknown action")


def _open_release(x: Instrument) -> ReleaseRequest:
    r = next((r for r in reversed(x.releases) if r.status in ("REQUESTED", "RECOMMENDED", "APPROVED")), None)
    if r is None:
        raise WorkflowError("There is no release request in progress.")
    return r


@router.get("/{inst_id}/discrepancies")
def list_discrepancies(inst_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [discrepancy_out(d) for d in load(db, inst_id, user).discrepancies]


@router.get("/{inst_id}/releases")
def list_releases(inst_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [release_out(r) for r in load(db, inst_id, user).releases]
