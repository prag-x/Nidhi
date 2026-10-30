"""Automatic checks on an instrument.

Each rule looks at one thing, explains itself in plain words and names the evidence. Checks run on submission,
after every rectification, after the document is read and after every bank reply. Findings that no longer hold are
closed automatically; findings recorded by an officer are never touched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import local_date, today, utcnow
from ..enums import (
    CLOSED_STATUSES,
    PENDING_SCRUTINY,
    SEVERITY_RANK,
    AlertKind,
    DiscrepancyStatus,
    EventType,
    InstrumentKind,
    Severity,
    Status,
    VerificationStatus,
)
from ..models import Discrepancy, Document, Instrument
from .settings import get_setting

IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
AUTO_SOURCES = ("RULE", "DOCUMENT", "BANK")

RULES = {
    "AMOUNT_SHORT": ("Amount below the requirement", Severity.HIGH),
    "VALIDITY_SHORT": ("Validity shorter than required", Severity.HIGH),
    "MATURED_ON_SUBMISSION": ("Already matured when submitted", Severity.HIGH),
    "DATES_INCONSISTENT": ("Dates do not make sense", Severity.MEDIUM),
    "LIEN_MISSING": ("Not pledged in AICTE's favour", Severity.HIGH),
    "NAME_MISMATCH": ("Depositor name does not match the institution", Severity.MEDIUM),
    "IFSC_INVALID": ("IFSC is not valid", Severity.MEDIUM),
    "IFSC_BANK_MISMATCH": ("IFSC belongs to a different bank", Severity.MEDIUM),
    "BANK_UNKNOWN": ("Issuing bank not recognised", Severity.MEDIUM),
    "BANK_NOT_SCHEDULED": ("Bank is not a scheduled bank", Severity.HIGH),
    "DOCUMENT_MISSING": ("Copy of the FDR not uploaded", Severity.MEDIUM),
    "DUPLICATE_INSTRUMENT": ("Same FDR already lodged with AICTE", Severity.CRITICAL),
    "DUPLICATE_DOCUMENT": ("Identical document lodged for another instrument", Severity.CRITICAL),
    "DOCUMENT_MISMATCH": ("Uploaded document differs from what was declared", Severity.HIGH),
    "BANK_MISMATCH": ("Bank's record differs from what was declared", Severity.HIGH),
    "BANK_NOT_FOUND": ("Bank has no record of this FDR", Severity.CRITICAL),
    "BANK_CLOSED": ("Bank reports the FDR closed or lien removed", Severity.CRITICAL),
    "OFFICER": ("Observation by the dealing officer", Severity.MEDIUM),
}
FRAUD_CODES = {"DUPLICATE_INSTRUMENT", "DUPLICATE_DOCUMENT", "BANK_NOT_FOUND", "BANK_CLOSED"}

FIELD_LABELS = {
    "fdr_number": "FDR number", "amount": "Amount", "issue_date": "Issue date", "maturity_date": "Maturity date",
    "depositor_name": "Depositor", "lien_holder": "Lien in favour of", "ifsc": "IFSC", "branch": "Branch",
    "bank": "Bank",
}


@dataclass
class Finding:
    code: str
    message: str
    field: str | None = None
    expected: str | None = None
    found: str | None = None
    source: str = "RULE"
    related_instrument_id: int | None = None
    severity: str | None = None

    @property
    def key(self) -> tuple:
        return (self.code, self.field, self.related_instrument_id)


def rupees(x: float | None) -> str:
    if x is None:
        return "—"
    n = int(round(x))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return f"Rs {s}"


# Characters that scanners and OCR confuse; an FDR number read as "7004..." is the same as "T004...".
_OCR_FOLD = str.maketrans("OQDILSBTZG", "0001158726")


def _norm_fdr(x: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (x or "").upper()).translate(_OCR_FOLD).lstrip("0")


NAME_FILLER = {"regd", "registered", "charitable", "public", "memorial", "india", "limited", "private"}


def _name_score(a: str, b: str) -> float:
    def clean(s):
        s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
        s = re.sub(r"\b(the|m s|ms|shri|shree|sri|smt|trust|society|educational|education|foundation)\b", " ", s)
        return " ".join(s.split())

    a, b = clean(a), clean(b)
    if not a or not b:
        return 0.0
    base = max(fuzz.token_set_ratio(a, b), fuzz.partial_ratio(a, b)) / 100.0
    # A distinctive word on one side only ("Sri Tapasya Vidya Trust" against "Tapasya Education Society") means a
    # different body, even when the shared word matches perfectly. Abbreviations and spelling variants still match.
    ta, tb = a.split(), b.split()

    def matched(tok, others):
        return any(o.startswith(tok) or tok.startswith(o) or fuzz.ratio(tok, o) >= 85 for o in others)

    extra = [t for t in ta if len(t) >= 4 and t not in NAME_FILLER and not matched(t, tb)] + \
            [t for t in tb if len(t) >= 4 and t not in NAME_FILLER and not matched(t, ta)]
    return max(0.0, base - 0.3 * len(extra))


def lien_ok(text: str | None, required: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return "aicte" in t or "all india council" in t or _name_score(text, required) >= 0.9


def compare_values(field: str, declared, other) -> bool:
    """True if two values for a field agree (formatting differences ignored)."""
    if other is None or declared is None:
        return True
    if field == "amount":
        return abs(float(declared) - float(other)) < 1
    if field == "fdr_number":
        return _norm_fdr(str(declared)) == _norm_fdr(str(other))
    if field in ("issue_date", "maturity_date"):
        return str(declared)[:10] == str(other)[:10]
    if field in ("depositor_name", "lien_holder", "branch"):
        return _name_score(str(declared), str(other)) >= 0.85
    return str(declared).strip().upper() == str(other).strip().upper()


def _fmt(field: str, v) -> str:
    if v is None:
        return "—"
    if field == "amount":
        return rupees(float(v))
    return str(v)


def evaluate(db: Session, inst: Instrument) -> list[Finding]:
    """Run every rule against the instrument as it stands now."""
    out: list[Finding] = []
    required_lien = str(get_setting(db, "lien_holder_text"))
    is_fdr = inst.kind == InstrumentKind.FDR

    if inst.required_amount and inst.amount + 0.5 < inst.required_amount:
        out.append(Finding("AMOUNT_SHORT", f"Deposit of {rupees(inst.amount)} is less than the {rupees(inst.required_amount)} "
                           f"required for this purpose.", "amount", rupees(inst.required_amount), rupees(inst.amount)))
    if inst.issue_date and inst.maturity_date and inst.maturity_date <= inst.issue_date:
        out.append(Finding("DATES_INCONSISTENT", "Maturity date is on or before the issue date.", "maturity_date",
                           f"after {inst.issue_date}", str(inst.maturity_date)))
    elif inst.issue_date and inst.issue_date > local_date(inst.submitted_at):
        out.append(Finding("DATES_INCONSISTENT", "Issue date is later than the date of submission.", "issue_date",
                           f"on or before {local_date(inst.submitted_at)}", str(inst.issue_date)))
    if is_fdr and inst.required_valid_until and inst.maturity_date < inst.required_valid_until:
        out.append(Finding("VALIDITY_SHORT", f"Matures on {inst.maturity_date:%d %b %Y}; it must stay valid until at least "
                           f"{inst.required_valid_until:%d %b %Y}.", "maturity_date",
                           f"{inst.required_valid_until}", str(inst.maturity_date)))
    if is_fdr and inst.maturity_date and inst.maturity_date < local_date(inst.submitted_at):
        out.append(Finding("MATURED_ON_SUBMISSION", "The FDR had already matured when it was submitted.",
                           "maturity_date", f"after {local_date(inst.submitted_at)}", str(inst.maturity_date)))
    if is_fdr and not lien_ok(inst.lien_holder, required_lien):
        out.append(Finding("LIEN_MISSING", f"The FDR must be marked under lien to “{required_lien}”.", "lien_holder",
                           required_lien, inst.lien_holder or "not marked"))

    # Depositor should be the institution or the society/trust that runs it.
    threshold = float(get_setting(db, "name_match_threshold"))
    names = [inst.institution.name] + ([inst.institution.society_name] if inst.institution.society_name else [])
    best = max(_name_score(inst.depositor_name or "", n) for n in names)
    if best < threshold:
        out.append(Finding("NAME_MISMATCH", f"Depositor “{inst.depositor_name}” does not match the institution or its "
                           f"society ({round(best * 100)}% similar).", "depositor_name", " / ".join(names),
                           inst.depositor_name))

    if is_fdr:
        if inst.bank is None:
            out.append(Finding("BANK_UNKNOWN", "The issuing bank could not be identified from the name or IFSC.", "bank",
                               "a listed bank", inst.bank_name_raw or "—"))
        elif not inst.bank.is_scheduled:
            out.append(Finding("BANK_NOT_SCHEDULED", f"{inst.bank.name} is not a scheduled bank.", "bank",
                               "a scheduled commercial bank", inst.bank.name))
        ifsc = (inst.ifsc or "").upper()
        if ifsc and not IFSC_RE.match(ifsc):
            out.append(Finding("IFSC_INVALID", "IFSC must be 4 letters, a zero, then 6 letters or digits.", "ifsc",
                               "e.g. SBIN0001234", ifsc))
        elif ifsc and inst.bank and ifsc[:4] != inst.bank.code:
            out.append(Finding("IFSC_BANK_MISMATCH", f"IFSC {ifsc} belongs to bank code {ifsc[:4]}, not {inst.bank.short_name}.",
                               "ifsc", f"{inst.bank.code}0……", ifsc))

    fdr_docs = [d for d in inst.documents if d.doc_type == "FDR_COPY"]
    if is_fdr and not fdr_docs:
        out.append(Finding("DOCUMENT_MISSING", "A scanned copy of the FDR has not been uploaded.", None, "PDF or image",
                           "none"))

    # Same FDR lodged elsewhere (another institution, or the same one twice).
    if is_fdr and inst.bank_id and inst.fdr_number:
        key = _norm_fdr(inst.fdr_number)
        others = db.scalars(select(Instrument).where(
            Instrument.bank_id == inst.bank_id, Instrument.id != inst.id, Instrument.fdr_key == key,
            Instrument.status.not_in([Status.REJECTED, Status.RELEASED]),
        )).all()
        for o in others:
            # Only the later lodgement is flagged; the earlier one is the original.
            if o.submitted_at and inst.submitted_at and o.submitted_at > inst.submitted_at:
                continue
            if _norm_fdr(o.fdr_number) == key and o.id != inst.replaces_id:
                whose = ("the same institution" if o.institution_id == inst.institution_id
                         else f"{o.institution.name}, {o.institution.city}")
                out.append(Finding("DUPLICATE_INSTRUMENT", f"FDR {inst.fdr_number} of {inst.bank.short_name} is already lodged "
                                   f"as {o.ref_no} by {whose}.", "fdr_number", "a fresh FDR", o.ref_no,
                                   related_instrument_id=o.id))
    # Identical file lodged for a different instrument.
    for d in fdr_docs:
        twin = db.scalar(select(Document).where(Document.sha256 == d.sha256, Document.instrument_id != inst.id)
                         .limit(1))
        other = db.get(Instrument, twin.instrument_id) if twin is not None else None
        if other is not None and other.id != inst.replaces_id and other.submitted_at <= inst.submitted_at:
            out.append(Finding("DUPLICATE_DOCUMENT", f"The uploaded file is byte-for-byte identical to the one lodged for "
                               f"{other.ref_no} ({other.institution.name}, {other.institution.city}).", None, "a document for this FDR",
                               other.ref_no, related_instrument_id=other.id))

    # Document says something different from the declaration.
    ex = inst.doc_extract or {}
    for field in ("fdr_number", "amount", "issue_date", "maturity_date", "depositor_name"):
        if field in ex and ex[field] not in (None, "") and not compare_values(field, getattr(inst, field), ex[field]):
            out.append(Finding("DOCUMENT_MISMATCH", f"{FIELD_LABELS[field]} on the uploaded FDR reads {_fmt(field, ex[field])}, "
                               f"but {_fmt(field, getattr(inst, field))} was declared.", field,
                               _fmt(field, getattr(inst, field)), _fmt(field, ex[field]), source="DOCUMENT"))

    # Bank's own record.
    latest = next((v for v in reversed(inst.verifications) if v.status != "REQUESTED"), None)
    if latest is not None:
        if latest.status == VerificationStatus.NOT_FOUND:
            out.append(Finding("BANK_NOT_FOUND", f"{inst.bank.short_name if inst.bank else 'The bank'} reports no FDR numbered "
                               f"{inst.fdr_number}.", "fdr_number", inst.fdr_number, "no record", source="BANK"))
        else:
            bv = latest.bank_values or {}
            if bv.get("status") in ("CLOSED",) or (bv.get("lien_holder") is not None
                                                   and not lien_ok(bv.get("lien_holder"), required_lien)):
                out.append(Finding("BANK_CLOSED", "The bank reports this FDR as closed or no longer under AICTE's lien"
                                   + (f" (closed on {bv.get('closed_on')})." if bv.get("closed_on") else "."), "lien_holder",
                                   "live, under AICTE lien", bv.get("status") or bv.get("lien_holder"), source="BANK"))
            for diff in latest.differences or []:
                f = diff["field"]
                if f == "lien_holder":
                    continue
                out.append(Finding("BANK_MISMATCH", f"{FIELD_LABELS.get(f, f)} per the bank is {_fmt(f, diff['bank'])}; "
                                   f"{_fmt(f, diff['declared'])} was declared.", f, _fmt(f, diff["declared"]),
                                   _fmt(f, diff["bank"]), source="BANK"))
    return out


def run_and_sync(db: Session, inst: Instrument, *, at=None, user=None) -> dict:
    """Evaluate the rules, open new findings, close those that no longer apply, and record what changed."""
    from .alerts import raise_alert
    from .instruments import record_event

    if inst.status in CLOSED_STATUSES:
        return {"raised": 0, "closed": 0}
    db.refresh(inst, ["documents", "verifications", "discrepancies", "institution", "bank"])
    findings = evaluate(db, inst)
    current = {f.key: f for f in findings}
    existing = [d for d in inst.discrepancies if d.source in AUTO_SOURCES and d.status == DiscrepancyStatus.OPEN]
    existing_keys = {(d.code, d.field, d.related_instrument_id): d for d in existing}
    raised, closed = [], []
    now = at or utcnow()
    for key, f in current.items():
        if key in existing_keys:
            continue
        title, sev = RULES[f.code]
        d = Discrepancy(instrument_id=inst.id, code=f.code, severity=f.severity or sev, field=f.field, message=f.message,
                        expected=f.expected, found=f.found, source=f.source,
                        related_instrument_id=f.related_instrument_id, raised_at=now)
        db.add(d)
        inst.discrepancies.append(d)
        raised.append(d)
    for key, d in existing_keys.items():
        if key not in current:
            d.status = DiscrepancyStatus.RESOLVED
            d.resolved_at = now
            d.resolution_note = "No longer applies after the latest information."
            closed.append(d)
    db.flush()
    refresh_summary(inst)
    if raised or closed:
        record_event(db, inst, EventType.CHECKS_RUN, user, actor_label=None if user else "Automatic checks", at=at,
                     meta={"raised": [d.code for d in raised], "closed": [d.code for d in closed]},
                     remarks=_summary(raised, closed))
    for d in raised:
        if d.code in FRAUD_CODES:
            raise_alert(db, kind=AlertKind.FRAUD_SIGNAL, severity=Severity.CRITICAL,
                        title=f"{RULES[d.code][0]}: {inst.ref_no}", message=d.message,
                        dedup_key=f"fraud:{inst.id}:{d.code}:{d.related_instrument_id or ''}",
                        instrument_id=inst.id, institution_id=inst.institution_id, target_role="RB_HEAD")
    return {"raised": len(raised), "closed": len(closed)}


def _summary(raised, closed) -> str:
    parts = []
    if raised:
        parts.append("Found: " + "; ".join(RULES[d.code][0] for d in raised))
    if closed:
        parts.append("Cleared: " + "; ".join(RULES[d.code][0] for d in closed))
    return ". ".join(parts) + "."


def refresh_summary(inst: Instrument) -> None:
    open_ = [d for d in inst.discrepancies if d.status == DiscrepancyStatus.OPEN]
    inst.open_discrepancies = len(open_)
    inst.max_severity = max((d.severity for d in open_), key=lambda s: SEVERITY_RANK[s], default=None)


def resolve(db: Session, inst: Instrument, d: Discrepancy, user, note: str, *, waive: bool = False) -> None:
    from .instruments import record_event

    if d.status != DiscrepancyStatus.OPEN:
        raise ValueError("This discrepancy is already closed.")
    d.status = DiscrepancyStatus.WAIVED if waive else DiscrepancyStatus.RESOLVED
    d.resolved_at = utcnow()
    d.resolved_by_id = user.id
    d.resolution_note = note
    refresh_summary(inst)
    record_event(db, inst, EventType.DISCREPANCY_WAIVED if waive else EventType.DISCREPANCY_RESOLVED, user,
                 remarks=f"{RULES[d.code][0]}: {note}", meta={"discrepancy_id": d.id, "code": d.code})


def raise_manual(db: Session, inst: Instrument, user, message: str, field: str | None = None,
                 severity: str = Severity.MEDIUM) -> Discrepancy:
    from .instruments import record_event

    d = Discrepancy(instrument_id=inst.id, code="OFFICER", severity=severity, field=field, message=message,
                    source="OFFICER", raised_at=utcnow())
    db.add(d)
    inst.discrepancies.append(d)
    db.flush()
    refresh_summary(inst)
    record_event(db, inst, EventType.DISCREPANCY_RAISED, user, remarks=message, meta={"discrepancy_id": d.id})
    return d


def days_to_maturity(inst: Instrument) -> int:
    return (inst.maturity_date - today()).days
