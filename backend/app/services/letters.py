"""Letters the portal drafts: acknowledgement, bank verification request, rectification and lien release.

Each letter carries a short code and a QR code. Anyone holding the letter (a bank branch, an institution, an
auditor) can open /verify/<code> to confirm it was issued by the portal and has not been altered: the page shows
the letter's fingerprint (SHA-256) and current validity.
"""

from __future__ import annotations

import hashlib
import io
import secrets
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import get_settings
from . import vault
from ..db import local_date, utcnow
from ..enums import DiscrepancyStatus, EventType, LetterKind
from ..models import Instrument, Letter, User
from .checks import RULES, rupees

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

SUBJECTS = {
    LetterKind.ACKNOWLEDGEMENT: "Acknowledgement of {kind} {fdr} lodged with AICTE ({ref})",
    LetterKind.BANK_VERIFICATION: "Request to confirm FDR No. {fdr} and AICTE's lien ({ref})",
    LetterKind.RECTIFICATION: "Discrepancies in {kind} {fdr} lodged with AICTE ({ref})",
    LetterKind.LIEN_RELEASE: "Discharge of lien on FDR No. {fdr} ({ref})",
}


def new_code(db: Session) -> str:
    from sqlalchemy import select

    while True:
        code = "NDL-" + "".join(secrets.choice(ALPHABET) for _ in range(8))
        if db.scalar(select(Letter.id).where(Letter.code == code)) is None:
            return code


def verify_url(code: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/verify/{code}"


def _addressee(inst: Instrument, kind: str) -> tuple[str, list[str]]:
    if kind in (LetterKind.BANK_VERIFICATION, LetterKind.LIEN_RELEASE):
        bank = inst.bank.name if inst.bank else (inst.bank_name_raw or "The Bank")
        return f"The Branch Manager, {bank}", [f"{inst.branch or ''} Branch".strip(), f"IFSC: {inst.ifsc or '—'}"]
    i = inst.institution
    return f"The Principal / Director, {i.name}", [f"{i.city}, {i.state.name if i.state else i.state_code}",
                                                  f"AICTE Permanent ID: {i.aicte_pid}"]


def _body(inst: Instrument, kind: str) -> list[str]:
    i = inst.institution
    fdr = f"FDR No. {inst.fdr_number} dated {inst.issue_date:%d %b %Y} for {rupees(inst.amount)}"
    if kind == LetterKind.ACKNOWLEDGEMENT:
        return [
            f"This is to acknowledge that {fdr}, maturing on {inst.maturity_date:%d %b %Y}, has been lodged with AICTE "
            f"by {i.name} towards {inst.purpose.replace('_', ' ').lower()} for {inst.approval_year}.",
            f"It is registered as {inst.ref_no}. Its acceptance is subject to scrutiny and to confirmation by the "
            f"issuing bank. The status can be followed on the portal.",
        ]
    if kind == LetterKind.BANK_VERIFICATION:
        return [
            f"{i.name} ({i.city}) has lodged {fdr}, said to be issued by your branch in the name of "
            f"“{inst.depositor_name}” and maturing on {inst.maturity_date:%d %b %Y}.",
            "You are requested to confirm (a) that the deposit exists with these particulars, (b) that it is "
            "marked under lien in favour of the Member Secretary, AICTE, and (c) that it will not be paid, renewed "
            "with change of lien, or closed prematurely without AICTE's written consent.",
            "Please quote the reference above in your reply.",
        ]
    if kind == LetterKind.RECTIFICATION:
        lines = [f"On scrutiny of {fdr} ({inst.ref_no}), the following need to be rectified:"]
        for n, d in enumerate([d for d in inst.discrepancies if d.status == DiscrepancyStatus.OPEN], 1):
            lines.append(f"{n}. {RULES[d.code][0]}: {d.message}")
        lines.append("Please submit the rectified instrument or clarification on the portal within 15 days.")
        return lines
    return [
        f"AICTE's lien on {fdr}, issued in the name of “{inst.depositor_name}” and registered with us as "
        f"{inst.ref_no}, is hereby discharged with the approval of the competent authority.",
        "The deposit may be paid or renewed as per the depositor's instructions. AICTE has no further claim on it.",
    ]


def render_pdf(inst: Instrument, kind: str, code: str, issued_by: User | None, issued_on) -> bytes:
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    w, h = A4
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"{code} {kind}")
    c.setFillColor(HexColor("#0F2A47"))
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, h - 22 * mm, "All India Council for Technical Education")
    c.setFont("Helvetica", 9.5)
    c.drawString(20 * mm, h - 28 * mm, "Regulation Bureau  ·  Security Deposit / FDR Management (Nidhi)")
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, h - 33 * mm, "Demonstration letter generated from synthetic data")
    c.setStrokeColor(HexColor("#94A3B8"))
    c.line(20 * mm, h - 36 * mm, w - 20 * mm, h - 36 * mm)

    c.setFillColor(HexColor("#0F172A"))
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, h - 46 * mm, f"Ref: {code}")
    c.drawRightString(w - 20 * mm, h - 46 * mm, f"Date: {issued_on:%d %B %Y}")
    to, extra = _addressee(inst, kind)
    y = h - 58 * mm
    c.drawString(20 * mm, y, "To,")
    for line in [to, *extra]:
        y -= 5.5 * mm
        c.drawString(20 * mm, y, line)
    y -= 10 * mm
    subject = SUBJECTS[kind].format(kind="FDR" if inst.kind == "FDR" else "security deposit", fdr=inst.fdr_number,
                                    ref=inst.ref_no)
    c.setFont("Helvetica-Bold", 10)
    for line in simpleSplit(f"Subject: {subject}", "Helvetica-Bold", 10, w - 40 * mm):
        c.drawString(20 * mm, y, line)
        y -= 5.5 * mm
    y -= 4 * mm
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, "Sir / Madam,")
    y -= 8 * mm
    for para in _body(inst, kind):
        for line in simpleSplit(para, "Helvetica", 10, w - 40 * mm):
            c.drawString(20 * mm, y, line)
            y -= 5.2 * mm
        y -= 3 * mm
    y -= 8 * mm
    c.drawString(20 * mm, y, "Yours faithfully,")
    y -= 14 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, issued_by.full_name if issued_by else "Regulation Bureau")
    c.setFont("Helvetica", 9.5)
    c.drawString(20 * mm, y - 5 * mm, issued_by.designation if issued_by else "AICTE")

    url = verify_url(code)
    qr = QrCodeWidget(url)
    b = qr.getBounds()
    size = 34 * mm
    d = Drawing(size, size, transform=[size / (b[2] - b[0]), 0, 0, size / (b[3] - b[1]), 0, 0])
    d.add(qr)
    renderPDF.draw(d, c, w - 20 * mm - size, 20 * mm)
    c.setFont("Helvetica", 7.5)
    c.drawRightString(w - 20 * mm, 17 * mm, "Scan to confirm this letter is genuine")
    c.drawString(20 * mm, 24 * mm, f"Verify at {url}")
    c.drawString(20 * mm, 20 * mm, "Generated by the portal. A changed copy will not match its registered fingerprint.")
    c.showPage()
    c.save()
    return buf.getvalue()


def issue_letter(db: Session, inst: Instrument, kind: str, user: User | None, *, at=None) -> Letter:
    from .instruments import record_event

    code = new_code(db)
    issued = at or utcnow()
    db.refresh(inst, ["institution", "bank", "discrepancies"])
    pdf = render_pdf(inst, kind, code, user, local_date(issued))
    digest = hashlib.sha256(pdf).hexdigest()
    folder = Path(get_settings().upload_dir) / "letters"
    folder.mkdir(parents=True, exist_ok=True)
    stored = f"{code}.pdf"
    vault.write(folder / stored, pdf)
    to, _ = _addressee(inst, kind)
    subject = SUBJECTS[kind].format(kind="FDR" if inst.kind == "FDR" else "security deposit", fdr=inst.fdr_number,
                                    ref=inst.ref_no)
    letter = Letter(code=code, kind=kind, instrument_id=inst.id, addressee=to, subject=subject, sha256=digest,
                    stored_name=stored, issued_at=issued, issued_by_id=user.id if user else None)
    db.add(letter)
    db.flush()
    record_event(db, inst, EventType.LETTER_ISSUED, user, at=at, actor_label=None if user else "System",
                 remarks=f"{subject}", meta={"letter": code, "kind": kind, "sha256": digest},
                 summary=f"Letter {code} issued")
    return letter


def letter_path(letter: Letter) -> Path:
    return Path(get_settings().upload_dir) / "letters" / letter.stored_name
