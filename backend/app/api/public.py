"""Public verification of letters issued by the portal. Anyone holding a letter (a bank branch, an institution, an
auditor) can scan its QR code or type its code to confirm that AICTE issued it and that the PDF is unaltered."""

import hashlib

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db, local_date
from ..models import Instrument, Letter
from ..security import public_track_limiter
from ..services.audit import client_ip

router = APIRouter(prefix="/public", tags=["public"])
NOT_FOUND = "No letter with this code was issued by the portal. Check the code printed beside the QR."
KIND_LABELS = {"ACKNOWLEDGEMENT": "Acknowledgement of FDR received", "BANK_VERIFICATION": "Request to confirm an FDR",
               "RECTIFICATION": "Request to rectify discrepancies", "LIEN_RELEASE": "Discharge of AICTE's lien"}


def _mask_fdr(n: str) -> str:
    return ("•" * max(0, len(n) - 4)) + n[-4:]


def _letter(db: Session, code: str) -> Letter:
    letter = db.scalar(select(Letter).where(func.upper(Letter.code) == code.strip().upper())
                       .options(selectinload(Letter.instrument).selectinload(Instrument.institution),
                                selectinload(Letter.instrument).selectinload(Instrument.bank)))
    if letter is None:
        raise HTTPException(404, NOT_FOUND)
    return letter


def _limit(request: Request) -> None:
    if not public_track_limiter.allow(client_ip(request) or "anon"):
        raise HTTPException(429, "Too many lookups. Please try again in a minute.")


@router.get("/verify/{code}")
def verify(code: str, request: Request, db: Session = Depends(get_db)):
    _limit(request)
    if not 6 <= len(code) <= 24:
        raise HTTPException(404, NOT_FOUND)
    letter = _letter(db, code)
    x = letter.instrument
    return {
        "code": letter.code, "kind": letter.kind, "kind_label": KIND_LABELS.get(letter.kind, letter.kind),
        "subject": letter.subject, "issued_on": local_date(letter.issued_at), "addressee": letter.addressee,
        "valid": not letter.revoked, "sha256": letter.sha256,
        "instrument": {"ref_no": x.ref_no, "institution": f"{x.institution.name}, {x.institution.city}",
                       "bank": x.bank.name if x.bank else x.bank_name_raw, "fdr_last4": _mask_fdr(x.fdr_number),
                       "amount": x.amount, "maturity_date": x.maturity_date},
    }


@router.post("/verify/{code}/file")
async def verify_file(code: str, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Compare an uploaded copy of the letter with the one the portal issued, byte for byte."""
    _limit(request)
    letter = _letter(db, code)
    data = await file.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "File larger than 5 MB")
    digest = hashlib.sha256(data).hexdigest()
    return {"code": letter.code, "matches": digest == letter.sha256, "uploaded_sha256": digest,
            "issued_sha256": letter.sha256}


