"""Measuring the checks and the document reader on fresh test cases whose faults are known in advance.

Checks: fresh submissions are generated against real institutions and banks, each with one deliberate fault (or
none): short amount, short validity, no lien, wrong depositor, bad IFSC, altered document, reused FDR, unknown at
the bank, bank record differs. The checks run exactly as in production, inside a transaction that is rolled back.
Precision: of the faults raised, how many were real. Recall: of the faults planted, how many were raised.

Reader: specimen FDRs in every layout with random values; each field read is compared with the truth. The same is
done for scanned copies (images, skewed and blurred) read by OCR.
"""

from __future__ import annotations

import random
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import today, utcnow
from ..enums import HELD_STATUSES, InstrumentKind
from ..models import AppSetting, Bank, BankRecord, Instrument, Verification
from . import bankgateway, checks, instruments
from .fdrdoc import STYLES, draw_specimen, read_fdr

KEY = "evaluation"
FAULTS = ["AMOUNT_SHORT", "VALIDITY_SHORT", "LIEN_MISSING", "NAME_MISMATCH", "IFSC_INVALID", "DOCUMENT_MISMATCH",
          "DUPLICATE_INSTRUMENT", "BANK_NOT_FOUND", "BANK_MISMATCH", None]
LIEN = "Member Secretary, AICTE"


def _check_cases(db: Session, n: int, seed: int) -> dict:
    rnd = random.Random(seed)
    from ..models import Institution

    institutions = db.scalars(select(Institution).where(Institution.society_name.is_not(None))).all()
    banks = db.scalars(select(Bank).where(Bank.is_scheduled.is_(True))).all()
    held = db.scalars(select(Instrument).where(Instrument.status.in_(HELD_STATUSES),
                                               Instrument.kind == InstrumentKind.FDR)).all()
    tp = fp = fn = 0
    clean_cases = clean_flagged = 0
    by_fault: dict[str, dict] = {}
    nested = db.begin_nested()
    try:
        for i in range(n):
            fault = FAULTS[i % len(FAULTS)]
            row = rnd.choice(institutions)
            bank = rnd.choice(banks)
            purpose = rnd.choice(["NEW_PROGRAMME", "INTAKE_INCREASE"])
            rule = instruments.applicable_rule(db, purpose, row.inst_type)
            issue = today() - timedelta(days=rnd.randint(1, 20))
            fdr = f"EV{seed}{i:05d}{rnd.randint(100, 999)}"
            inst = Instrument(kind=InstrumentKind.FDR, institution_id=row.id, purpose=purpose, approval_year="2026-27",
                              fdr_number=fdr, bank_id=bank.id, bank_name_raw=bank.name, branch=f"{row.city} Main Branch",
                              ifsc=f"{bank.code}0{rnd.randint(0, 999999):06d}", depositor_name=row.society_name,
                              amount=rule.amount, issue_date=issue,
                              maturity_date=issue + relativedelta(months=rule.min_tenure_months), lien_holder=LIEN,
                              submitted_at=utcnow())
            doc_amount = inst.amount
            bank_amount = inst.amount
            if fault == "AMOUNT_SHORT":
                inst.amount = doc_amount = bank_amount = round(rule.amount * rnd.uniform(0.3, 0.9), -3)
            elif fault == "VALIDITY_SHORT":
                inst.maturity_date = issue + relativedelta(months=rule.min_tenure_months - rnd.randint(6, 18))
            elif fault == "LIEN_MISSING":
                inst.lien_holder = rnd.choice([None, "", "Self", "Branch Manager"])
            elif fault == "NAME_MISMATCH":
                inst.depositor_name = rnd.choice(["Prerana Infra Builders Pvt Ltd", "Shree Ganesh Traders",
                                                  "Om Sai Constructions", "Rajlaxmi Agencies"])
            elif fault == "IFSC_INVALID":
                inst.ifsc = rnd.choice([f"{bank.code}1{rnd.randint(0, 99999):05d}X", f"{bank.code}0{rnd.randint(0, 999):03d}",
                                        f"12340{rnd.randint(0, 999999):06d}"])
            elif fault == "DOCUMENT_MISMATCH":
                doc_amount = round(inst.amount * rnd.choice([0.1, 0.5, 0.75]), -3)
            elif fault == "DUPLICATE_INSTRUMENT" and held:
                other = rnd.choice(held)
                inst.bank_id, inst.fdr_number = other.bank_id, other.fdr_number
                bank = db.get(Bank, other.bank_id)
                inst.ifsc = f"{bank.code}0{rnd.randint(0, 999999):06d}"
            elif fault == "BANK_MISMATCH":
                bank_amount = round(inst.amount * rnd.choice([0.2, 0.5, 0.8]), -3)
            db.add(inst)
            db.flush()
            db.refresh(inst, ["institution", "bank"])
            instruments.required_terms(db, inst)
            if fault != "BANK_NOT_FOUND" and fault != "DUPLICATE_INSTRUMENT":
                db.add(BankRecord(bank_id=inst.bank_id, fdr_number=inst.fdr_number, branch=inst.branch, ifsc=inst.ifsc,
                                  depositor_name=inst.depositor_name, amount=bank_amount, issue_date=inst.issue_date,
                                  maturity_date=inst.maturity_date, lien_holder=inst.lien_holder or None, status="LIVE"))
                db.flush()
            pdf = draw_specimen(bank_name=bank.name, branch=inst.branch, ifsc=inst.ifsc or "", fdr_number=inst.fdr_number,
                                amount=doc_amount, issue_date=inst.issue_date, maturity_date=inst.maturity_date,
                                depositor=inst.depositor_name, lien_holder=inst.lien_holder or None, rate=7.0,
                                style=rnd.randrange(len(STYLES)))
            from ..models import Document

            import hashlib

            doc = Document(instrument_id=inst.id, doc_type="FDR_COPY", filename="eval.pdf",
                           stored_name=f"eval-{seed}-{i}.pdf", content_type="application/pdf", size_bytes=len(pdf),
                           sha256=hashlib.sha256(pdf + fdr.encode()).hexdigest())
            db.add(doc)
            inst.documents.append(doc)
            inst.doc_extract, inst.doc_extract_confidence = read_fdr(pdf)
            if fault != "DUPLICATE_INSTRUMENT":
                answer = bankgateway.GATEWAY.lookup(db, inst)
                v = Verification(instrument_id=inst.id, channel="GATEWAY", requested_at=utcnow(), responded_at=utcnow(),
                                 status="NOT_FOUND" if not answer.found else "CONFIRMED", bank_values=answer.values)
                if answer.found:
                    v.differences = bankgateway.differences(inst, answer.values)
                    v.status = "MISMATCH" if v.differences else "CONFIRMED"
                db.add(v)
                inst.verifications.append(v)
            found = {f.code for f in checks.evaluate(db, inst)} & set(c for c in FAULTS if c)
            expected = {fault} if fault else set()
            if fault == "AMOUNT_SHORT":
                found.discard("BANK_MISMATCH")
            hit = len(found & expected)
            tp += hit
            fp += len(found - expected)
            fn += len(expected - found)
            stats = by_fault.setdefault(fault or "CLEAN", {"cases": 0, "caught": 0, "false_alarms": 0})
            stats["cases"] += 1
            stats["caught"] += hit
            stats["false_alarms"] += len(found - expected)
            if fault is None:
                clean_cases += 1
                clean_flagged += bool(found)
    finally:
        nested.rollback()
    return {
        "cases": n,
        "precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "clean_cases": clean_cases,
        "clean_flagged": clean_flagged,
        "by_fault": by_fault,
    }


def _scan(pdf: bytes, rnd: random.Random) -> bytes:
    """Turn a specimen into what a scanner or phone produces: a 200 dpi greyscale image, slightly skewed and soft."""
    import io

    import pypdfium2 as pdfium
    from PIL import ImageFilter

    img = pdfium.PdfDocument(pdf)[0].render(scale=200 / 72).to_pil().convert("L")
    img = img.rotate(rnd.uniform(-1.5, 1.5), expand=True, fillcolor=255).filter(ImageFilter.GaussianBlur(0.6))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _reader(n: int, seed: int, scanned: bool = False) -> dict:
    from datetime import date

    rnd = random.Random(seed + (1000 if scanned else 0))
    correct = total = exact = 0
    by_field: dict[str, list[int]] = {}
    for i in range(n):
        issue = date(2026, 1, 1) + timedelta(days=rnd.randint(0, 300))
        truth = {
            "fdr_number": rnd.choice([f"{rnd.randint(30, 49)}{rnd.randint(100000000, 999999999)}",
                                      f"FD/2026/{rnd.randint(10000, 99999)}", f"TD-{rnd.randint(100000, 999999)}-26"]),
            "amount": float(rnd.choice([150000, 300000, 500000, 750000, 1000000, 1500000, 2500000])
                            + rnd.choice([0, 0, 0, 500, 1250])),
            "issue_date": issue.isoformat(),
            "maturity_date": (issue + relativedelta(months=rnd.choice([36, 48, 60, 72]))).isoformat(),
            "depositor_name": rnd.choice(["Kadamb Shikshan Prasarak Mandal", "Udaan Educational Trust",
                                          "Sri Tapasya Vidya Trust", "Medhavi Education Society",
                                          "Ramdas Kulkarni Memorial Trust"]),
            "lien_holder": LIEN,
        }
        pdf = draw_specimen(bank_name="Vindhya Bank", branch="Main Branch", ifsc="VNDB0001234",
                            fdr_number=truth["fdr_number"], amount=truth["amount"],
                            issue_date=date.fromisoformat(truth["issue_date"]),
                            maturity_date=date.fromisoformat(truth["maturity_date"]), depositor=truth["depositor_name"],
                            lien_holder=LIEN, rate=rnd.choice([6.5, 7.0, 7.25]), style=i % len(STYLES))
        got, _conf = read_fdr(_scan(pdf, rnd), ".png") if scanned else read_fdr(pdf)
        ok_all = True
        for f, v in truth.items():
            ok = checks.compare_values(f, v, got.get(f)) and got.get(f) is not None
            by_field.setdefault(f, [0, 0])
            by_field[f][0] += ok
            by_field[f][1] += 1
            correct += ok
            total += 1
            ok_all &= ok
        exact += ok_all
    return {
        "documents": n,
        "layouts": len(STYLES),
        "field_accuracy": round(correct / total, 3),
        "documents_fully_read": round(exact / n, 3),
        "by_field": {f: round(a / b, 3) for f, (a, b) in by_field.items()},
    }


def evaluate_and_store(db: Session, n_checks: int = 500, n_docs: int = 300, seed: int = 31, n_scans: int = 45) -> dict:
    from .fdrdoc import ocr_available

    result = {"checks": _check_cases(db, n_checks, seed), "reader": _reader(n_docs, seed),
              "run_at": utcnow().isoformat()}
    if n_scans and ocr_available():
        result["scanned"] = _reader(n_scans, seed, scanned=True)
    row = db.get(AppSetting, KEY)
    if row is None:
        db.add(AppSetting(key=KEY, value=result))
    else:
        row.value = result
    return result


def stored(db: Session) -> dict | None:
    row = db.get(AppSetting, KEY)
    return row.value if row else None
