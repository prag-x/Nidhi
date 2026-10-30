"""Deterministic demo dataset.

Creates master data, 600 fictional institutions, 11 fictional banks and roughly a decade of security deposits and
FDRs: lodged, verified with the bank, accepted, reminded, renewed late or on time, and occasionally released. Every
instrument goes through the same services as the live system, so the histories, checks, hash chains and alerts are
genuine. A handful of scenarios are planted for the demo walkthrough.
"""

from __future__ import annotations

import hashlib
import random
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import today, utcnow
from ..enums import InstrumentKind, ReleaseReason, Role, Status
from ..matching.institutions import invalidate_index
from ..matching.normalize import normalize_name
from ..models import (
    Alert,
    Bank,
    BankRecord,
    DepositRule,
    Document,
    Institution,
    InstitutionAlias,
    Instrument,
    InstrumentEvent,
    OrgUnit,
    Region,
    State,
    User,
)
from ..security import hash_password
from ..services import bankgateway, instruments, release
from ..services.fdrdoc import draw_specimen, read_fdr
from . import data as D

DEMO_PASSWORD = "Demo@2026"
LIEN = "Member Secretary, AICTE"

USERS = [
    ("admin", "Rakesh Bhatnagar", "System Administrator (e-Governance)", Role.ADMIN, None),
    ("ms", "Dr. Kavita Sood", "Member Secretary (Competent Authority)", Role.COMPETENT_AUTHORITY, "MGMT"),
    ("auditor", "Smt. Revathi Iyer", "Internal Audit & Vigilance Observer", Role.AUDITOR, None),
    ("rb.head", "Shri Vikram Sinha", "Director, Regulation Bureau", Role.RB_HEAD, "RB"),
    ("rb.officer1", "Smt. Neelam Arora", "Deputy Director", Role.RB_OFFICER, "RB"),
    ("rb.officer2", "Shri Imran Qureshi", "Assistant Director", Role.RB_OFFICER, "RB"),
    ("rb.officer3", "Ms. Priyanka Rawat", "Section Officer", Role.RB_OFFICER, "RB"),
    ("rb.officer4", "Shri Manoj Kumar", "Section Officer", Role.RB_OFFICER, "RB"),
    ("accounts", "Shri Pankaj Goel", "Deputy Director (Finance & Accounts)", Role.ACCOUNTS, "FIN"),
]
RO_OFFICERS = {
    "WRO": "Ms. Pallavi Shinde", "SRO": "Shri Karthik Raman", "SWRO": "Ms. Shwetha Gowda", "TVRO": "Shri Anoop Nair",
    "CRO": "Ms. Ruchi Jain", "NWRO": "Shri Harjeet Gill", "NRO": "Ms. Nidhi Awasthi", "ERO": "Shri Arnab Sen",
    "SCRO": "Ms. Sravani Reddy", "NERO": "Shri Dipankar Kalita", "GRO": "Ms. Neha Dahiya", "VRO": "Shri Chirag Patel",
}

# Planted institutions: name, state, city, type, society, institution-user handle
PLANTED = [
    ("Kadamb Institute of Technology", "MH", "Nashik", "Engineering & Technology", "Kadamb Shikshan Prasarak Mandal",
     "kadamb"),
    ("Kadamb College of Pharmacy", "MH", "Nashik", "Pharmacy", "Kadamb Shikshan Prasarak Mandal", None),
    ("Udaan Institute of Management", "UP", "Lucknow", "Management", "Udaan Educational Trust", "udaan"),
    ("Tapasya College of Engineering", "AP", "Visakhapatnam", "Engineering & Technology", "Tapasya Education Society",
     None),
    ("Tapasya College of Engineering", "AP", "Vijayawada", "Engineering & Technology", "Sri Tapasya Vidya Trust", None),
    ("Shri Vidyadeep College of Engineering", "MH", "Pune", "Engineering & Technology", "Vidyadeep Shiksha Samiti",
     None),
    ("Saptarishi Polytechnic", "PB", "Ludhiana", "Diploma (Polytechnic)", "Saptarishi Charitable Trust", None),
    ("Nachiketa Institute of Engineering & Technology", "RJ", "Jaipur", "Engineering & Technology",
     "Nachiketa Education Foundation", None),
    ("Late Shri Ramdas Kulkarni Memorial College of Engineering", "KA", "Belagavi", "Engineering & Technology",
     "Ramdas Kulkarni Memorial Trust", None),
    ("Medhavi Institute of Management Studies", "TG", "Hyderabad", "Management", "Medhavi Education Society", None),
    ("Jagriti College of Pharmacy", "GJ", "Ahmedabad", "Pharmacy", "Jagriti Vidya Pratishthan", None),
    ("Pragyan Institute of Technology", "OD", "Bhubaneswar", "Engineering & Technology", "Pragyan Educational Trust",
     None),
]


@dataclass
class Ctx:
    rnd: random.Random
    today: date
    banks: dict[str, Bank]
    officers: list[User]
    head: User
    ca: User
    accounts: User
    inst_users: dict[int, User] = field(default_factory=dict)
    upload_dir: Path = Path(".")
    seq: int = 0
    lateness: dict[int, float] = field(default_factory=dict)   # institution id -> latent tendency to renew late
    home_bank: dict[int, str] = field(default_factory=dict)


def _at(day: date, rnd: random.Random, hour: tuple[int, int] = (10, 17)) -> datetime:
    from ..db import business_tz

    t = time(rnd.randint(*hour), rnd.randint(0, 59), rnd.randint(0, 59))
    return datetime.combine(day, t, tzinfo=business_tz()).astimezone(UTC)


# ---------------------------------------------------------------- master data


def _master(db: Session) -> None:
    regions = {}
    for code, name, city, address, lat, lon, states in D.REGIONS:
        r = Region(code=code, name=name, city=city, address=address, lat=lat, lon=lon)
        db.add(r)
        db.flush()
        regions[code] = r
        for st in states:
            db.add(State(code=st, name=D.STATES[st], region_id=r.id))
    for code, name, utype, region_code, desc in D.UNITS:
        db.add(OrgUnit(code=code, name=name, unit_type=utype, description=desc,
                       region_id=regions[region_code].id if region_code else None))
    for code, name, short, sector, channel, scheduled, aliases in D.BANKS:
        db.add(Bank(code=code, name=name, short_name=short, sector=sector, verify_channel=channel,
                    is_scheduled=scheduled, aliases=aliases))
    for purpose, itype, amount, tenure, note in D.DEPOSIT_RULES:
        db.add(DepositRule(purpose=purpose, inst_type=itype, amount=amount, min_tenure_months=tenure, note=note))
    db.flush()
    pw = hash_password(DEMO_PASSWORD)
    units = {u.code: u for u in db.scalars(select(OrgUnit))}
    for handle, name, desig, role, unit in USERS:
        db.add(User(email=f"{handle}@nidhi.test", full_name=name, designation=desig, role=role,
                    org_unit_id=units[unit].id if unit else None, password_hash=pw,
                    phone=f"011-2958{len(handle):02d}{ord(handle[0]) % 100:02d}"))
    for code, *_ in D.REGIONS:
        unit = units[f"RO-{code}"]
        db.add(User(email=f"ro.{code.lower()}@nidhi.test", full_name=RO_OFFICERS[code],
                    designation=f"Assistant Director, {unit.name.split(',')[0]}", role=Role.REGIONAL_OFFICER,
                    org_unit_id=unit.id, password_hash=pw))
    db.flush()


# ---------------------------------------------------------------- institutions


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())[:20]


def _new_pid(rnd: random.Random, used: set[str]) -> str:
    while True:
        pid = f"1-{rnd.randint(10_000_000, 9_999_999_999)}"
        if pid not in used:
            used.add(pid)
            return pid


def _institution(db, rnd, name, state, city_row, itype, ownership, intake, used_pids, pid=None) -> Institution:
    city, district, pin, lat, lon = city_row
    region_id = db.get(State, state).region_id
    pin_code = f"{pin[:3]}{(int(pin[3:]) + rnd.randint(0, 30)) % 1000:03d}"
    area = rnd.choice(["MIDC Area", "Station Road", "Ring Road", "NH Bypass", "Industrial Estate", "University Road",
                       f"Sector {rnd.randint(2, 62)}", "Outer Ring Road", "College Road", "Highway Road"])
    inst = Institution(
        aicte_pid=pid or _new_pid(rnd, used_pids), name=name, normalized_name=normalize_name(name).text,
        acronym="".join(w[0] for w in name.replace("&", "").split() if w[0].isupper())[:12],
        inst_type=itype, ownership=ownership, address=f"{rnd.randint(1, 250)}, {area}, {city} – {pin_code}",
        city=city, district=district, state_code=state, pincode=pin_code, region_id=region_id,
        established_year=rnd.randint(1965, 2021), approved_intake=intake,
        approval_status=rnd.choices(["APPROVED", "APPROVED", "APPROVED", "PROGRESSIVE_CLOSURE"], [70, 20, 8, 2])[0],
        email=f"principal.{_slug(name)}@inst.test", phone=f"0{rnd.randint(20, 99)}-{rnd.randint(2000000, 2999999)}",
        lat=lat + rnd.uniform(-0.06, 0.06), lon=lon + rnd.uniform(-0.06, 0.06),
    )
    db.add(inst)
    return inst


def _institutions(db: Session, rnd: random.Random, n: int) -> list[Institution]:
    used_names: set[tuple[str, str]] = set()
    used_pids: set[str] = set()
    states = list(D.STATE_WEIGHTS)
    weights = [D.STATE_WEIGHTS[s] for s in states]
    out: list[Institution] = []

    for name, st, city, itype, society, _handle in PLANTED:
        row = next(r for r in D.CITIES[st] if r[0] == city)
        inst = _institution(db, rnd, name, st, row, itype, "Private (Self-financing)", 420, used_pids)
        inst.society_name = society
        inst.approval_status = "APPROVED"
        out.append(inst)
        used_names.add((name, city))

    roots = list(D.NAME_ROOTS)
    while len(out) < n:
        st = rnd.choices(states, weights)[0]
        row = rnd.choice(D.CITIES[st])
        itype, _w, suffixes, (lo, hi) = rnd.choices(D.INST_TYPES, [t[1] for t in D.INST_TYPES])[0]
        suffix = rnd.choice(suffixes)
        if rnd.random() < 0.8:
            prefix = rnd.choices(["", "Shri ", "Sri ", "Smt. "], [80, 10, 6, 4])[0]
            name = f"{prefix}{rnd.choice(roots)} {suffix}"
        else:
            hon = rnd.choice(["Late Shri ", "Dr. ", "Smt. ", ""])
            name = f"{hon}{rnd.choice(D.FOUNDER_FIRST)} {rnd.choice(D.FOUNDER_LAST)} {rnd.choice(['Memorial ', ''])}{suffix}"
        if (name, row[0]) in used_names:
            continue
        used_names.add((name, row[0]))
        ownership = rnd.choices([o for o, _ in D.OWNERSHIP], [w for _, w in D.OWNERSHIP])[0]
        inst = _institution(db, rnd, name, st, row, itype, ownership, rnd.randrange(lo, hi, 30), used_pids)
        root = re.sub(r"^(Shri |Sri |Smt\. |Late Shri |Dr\. )", "", name).split()[0]
        inst.society_name = f"{rnd.choice(['', 'Shri ', 'Sri '])}{root} {rnd.choice(D.SOCIETY_FORMS)}".strip()
        out.append(inst)
    db.flush()
    return out


# ---------------------------------------------------------------- instruments


def _ifsc(rnd: random.Random, code: str) -> str:
    return f"{code}0{rnd.randint(0, 999999):06d}"


def _fdr_number(rnd: random.Random, code: str, year: int) -> str:
    style = sum(map(ord, code)) % 4
    if style == 0:
        return f"{rnd.randint(30, 49)}{rnd.randint(100000000, 999999999)}"
    if style == 1:
        return f"FD/{year}/{rnd.randint(10000, 99999)}"
    if style == 2:
        return f"{code[:2]}{year % 100:02d}{rnd.randint(1000000, 9999999)}"
    return f"TD-{rnd.randint(100000, 999999)}-{year % 100:02d}"


def _logit(x: float) -> float:
    import math

    return 1 / (1 + math.exp(-x))


def store_document(db: Session, ctx: Ctx, inst: Instrument, pdf: bytes, *, at: datetime, user: User | None,
                   filename: str | None = None, doc_type: str = "FDR_COPY") -> Document:
    stored = f"{uuid.uuid4().hex}.pdf"
    (ctx.upload_dir / stored).write_bytes(pdf)
    doc = Document(instrument_id=inst.id, doc_type=doc_type, filename=filename or f"FDR_{re.sub(r'[^A-Za-z0-9]', '', inst.fdr_number)}.pdf",
                   stored_name=stored, content_type="application/pdf", size_bytes=len(pdf),
                   sha256=hashlib.sha256(pdf).hexdigest(), uploaded_by_id=user.id if user else None, uploaded_at=at)
    db.add(doc)
    inst.documents.append(doc)
    return doc


def lodge(db: Session, ctx: Ctx, inst_row: Institution, *, purpose: str, approval_year: str, bank_code: str,
          issue: date, tenure_months: int, submitted: datetime, amount: float | None = None,
          replaces: Instrument | None = None, depositor: str | None = None, lien: str | None = LIEN,
          fdr_number: str | None = None, ifsc: str | None = None, bank_truth: str | dict = "same",
          doc_overrides: dict | None = None, doc_bytes: bytes | None = None, user: User | None = None,
          maturity: date | None = None, auto_renewal: bool | None = None, attach_doc: bool = True,
          kind: str = InstrumentKind.FDR) -> Instrument:
    """Lodge an instrument the way an institution does: declare, upload the FDR copy, submit."""
    rnd = ctx.rnd
    bank = ctx.banks[bank_code]
    rule = instruments.applicable_rule(db, purpose, inst_row.inst_type)
    amount = amount if amount is not None else (rule.amount if rule else 500_000)
    maturity = maturity or (issue + relativedelta(months=tenure_months))
    user = user or ctx.inst_users.get(inst_row.id)
    inst = Instrument(
        kind=kind, institution_id=inst_row.id, purpose=purpose, approval_year=approval_year,
        application_ref=f"APP-{approval_year[:4]}-{rnd.randint(100000, 999999)}",
        fdr_number=fdr_number or _fdr_number(rnd, bank_code, issue.year), bank_id=bank.id,
        bank_name_raw=bank.name, branch=f"{inst_row.city} {rnd.choice(D.BRANCH_AREAS)}",
        ifsc=ifsc or _ifsc(rnd, bank_code), depositor_name=depositor or inst_row.society_name or inst_row.name,
        amount=amount, issue_date=issue, maturity_date=maturity, lien_holder=lien,
        auto_renewal=rnd.random() < 0.35 if auto_renewal is None else auto_renewal,
        replaces_id=replaces.id if replaces else None, submitted_at=submitted,
    )
    db.add(inst)
    db.flush()
    truth = {"fdr_number": inst.fdr_number, "branch": inst.branch, "ifsc": inst.ifsc, "depositor_name": inst.depositor_name,
             "amount": inst.amount, "issue_date": inst.issue_date, "maturity_date": inst.maturity_date,
             "lien_holder": inst.lien_holder, "status": "LIVE", "auto_renewal": inst.auto_renewal, "closed_on": None}
    if isinstance(bank_truth, dict):
        truth.update(bank_truth)
    if bank_truth != "missing" and kind == InstrumentKind.FDR:
        db.add(BankRecord(bank_id=bank.id, **truth))
    if attach_doc and kind == InstrumentKind.FDR:
        if doc_bytes is None:
            dv = {"fdr_number": inst.fdr_number, "amount": inst.amount, "issue_date": inst.issue_date,
                  "maturity_date": inst.maturity_date, "depositor": inst.depositor_name, "lien_holder": inst.lien_holder}
            dv.update(doc_overrides or {})
            doc_bytes = draw_specimen(bank_name=bank.name, branch=inst.branch, ifsc=inst.ifsc, rate=rnd.choice([6.5, 6.8, 7.0, 7.1, 7.25]),
                                      style=sum(map(ord, bank_code)) % 3, **dv)
        store_document(db, ctx, inst, doc_bytes, at=submitted, user=user)
        inst.doc_extract, inst.doc_extract_confidence = read_fdr(doc_bytes)
    instruments.submit(db, inst, user, at=submitted)
    return inst


def process(db: Session, ctx: Ctx, inst: Instrument, *, rectify_after: int | None = None, accept: bool = True,
            stop_before_verify: bool = False) -> datetime | None:
    """Scrutiny, bank verification, rectification and acceptance, each at a plausible time; stops at 'now'."""
    from ..enums import EventType

    rnd = ctx.rnd
    now = utcnow()
    officer = inst.assigned_officer or ctx.officers[0]
    t = inst.submitted_at + timedelta(days=rnd.choice([0, 1, 1, 2, 3]), hours=rnd.randint(1, 5))
    if t > now:
        return None
    instruments.record_event(db, inst, EventType.SCRUTINY_STARTED, officer, to_status=Status.UNDER_SCRUTINY, at=t)
    if stop_before_verify:
        return None
    if inst.bank and inst.bank.verify_channel == "GATEWAY":
        bankgateway.verify_online(db, inst, officer, at=t + timedelta(minutes=rnd.randint(5, 90)))
        verified = t + timedelta(hours=2)
    else:
        bankgateway.request_by_letter(db, inst, officer, at=t + timedelta(minutes=30))
        verified = t + timedelta(days=rnd.randint(6, 24))
        if verified > now:
            return None
        rec = db.scalar(select(BankRecord).where(BankRecord.bank_id == inst.bank_id,
                                                 BankRecord.fdr_number == inst.fdr_number))
        values = None if rec is None else {
            "fdr_number": rec.fdr_number, "amount": rec.amount, "issue_date": rec.issue_date.isoformat(),
            "maturity_date": rec.maturity_date.isoformat(), "depositor_name": rec.depositor_name,
            "lien_holder": rec.lien_holder, "branch": rec.branch, "ifsc": rec.ifsc, "status": rec.status}
        bankgateway.record_reply(db, inst, officer, values, f"BR/{rnd.randint(1000, 9999)}/{verified.year}", at=verified)
    done = verified
    if rectify_after is not None:
        rt = inst.submitted_at + timedelta(days=rectify_after)
        if rt > now:
            if inst.open_discrepancies:
                instruments.record_event(db, inst, EventType.OBSERVATION, officer, to_status=Status.DISCREPANCY,
                                         at=max(verified, t) + timedelta(hours=3),
                                         remarks="Institution asked to rectify the discrepancies listed.")
            return None
        if inst.open_discrepancies:
            instruments.record_event(db, inst, EventType.OBSERVATION, officer, to_status=Status.DISCREPANCY,
                                     at=max(verified, t) + timedelta(hours=3),
                                     remarks="Institution asked to rectify the discrepancies listed.")
        inst.lien_holder = LIEN
        rec = db.scalar(select(BankRecord).where(BankRecord.bank_id == inst.bank_id, BankRecord.fdr_number == inst.fdr_number))
        if rec:
            rec.lien_holder = LIEN
        instruments.record_event(db, inst, EventType.RECTIFICATION_SUBMITTED, ctx.inst_users.get(inst.institution_id),
                                 actor_label=None if ctx.inst_users.get(inst.institution_id) else inst.institution.name,
                                 to_status=Status.UNDER_SCRUTINY, at=rt,
                                 remarks="Bank's lien-marking letter in favour of the Member Secretary, AICTE uploaded.")
        if inst.bank and inst.bank.verify_channel == "GATEWAY":
            bankgateway.verify_online(db, inst, officer, at=rt + timedelta(hours=4))
        else:
            from ..services.checks import run_and_sync

            v = inst.verifications[-1]
            v.bank_values = {**(v.bank_values or {}), "lien_holder": LIEN}
            run_and_sync(db, inst, at=rt + timedelta(hours=1))
        done = rt + timedelta(hours=5)
    if not accept:
        return None
    at = done + timedelta(days=rnd.choice([0, 1, 1, 2, 4]), hours=rnd.randint(1, 4))
    if at > now:
        return None
    if inst.open_discrepancies or inst.verification_status != "CONFIRMED":
        return None
    instruments.accept(db, inst, officer, at=at)
    return at


def _late_probability(ctx: Ctx, inst_row: Institution, bank_code: str, auto_renewal: bool, discrepancies: int) -> float:
    z = ctx.lateness[inst_row.id]
    letter = ctx.banks[bank_code].verify_channel == "LETTER"
    x = (-1.0 + 1.6 * z + 0.45 * ("Private" in inst_row.ownership) + 0.55 * letter + 0.35 * discrepancies
         + 0.9 * (inst_row.approval_status != "APPROVED") - 0.7 * auto_renewal)
    return _logit(x)


def chain(db: Session, ctx: Ctx, inst_row: Institution, purpose: str, start: date, *, max_generations: int = 6,
          release_prob: float = 0.03) -> list[Instrument]:
    """Simulate one deposit requirement over time: lodge, verify, accept, then renew (late or on time) or release."""
    rnd = ctx.rnd
    now = utcnow()
    out: list[Instrument] = []
    bank_code = ctx.home_bank[inst_row.id]
    issue = start
    prev: Instrument | None = None
    for _gen in range(max_generations):
        rule = instruments.applicable_rule(db, purpose, inst_row.inst_type)
        tenure = rule.min_tenure_months + (12 if rnd.random() < 0.2 else 0)
        submitted = _at(issue + timedelta(days=rnd.randint(1, 12)), rnd)
        if submitted > now:
            break
        year = issue.year if issue.month >= 4 else issue.year - 1
        lien_missing = rnd.random() < 0.14
        inst = lodge(db, ctx, inst_row, purpose=purpose, approval_year=f"{year}-{(year + 1) % 100:02d}",
                     bank_code=bank_code, issue=issue, tenure_months=tenure, submitted=submitted, replaces=prev,
                     lien=None if lien_missing else LIEN)
        out.append(inst)
        accepted = process(db, ctx, inst, rectify_after=rnd.randint(8, 25) if lien_missing else None)
        if accepted is None and submitted < now - timedelta(days=60):
            # Could not be accepted (e.g. a non-scheduled bank): rejected, and the institution lodges a fresh FDR
            # with a scheduled bank for the same requirement.
            when = submitted + timedelta(days=rnd.randint(20, 40))
            instruments.reject(db, inst, inst.assigned_officer or ctx.officers[0],
                               "Not acceptable as lodged; a fresh FDR from a scheduled bank is required.", at=when)
            bank_code = "BHRT" if bank_code == "DCNB" else bank_code
            issue = (when + timedelta(days=rnd.randint(5, 20))).date()
            continue
        if accepted is None:
            break
        maturity = inst.maturity_date
        # Release instead of renewal, now and then (closure of a programme, approval not granted).
        if rnd.random() < release_prob and maturity - timedelta(days=200) < today():
            when = _at(min(maturity - timedelta(days=rnd.randint(20, 150)), today() - timedelta(days=rnd.randint(10, 60))), rnd)
            if when > accepted + timedelta(days=30):
                _release(db, ctx, inst, when, ReleaseReason.CLOSURE if rnd.random() < 0.6 else ReleaseReason.PERIOD_COMPLETED)
                break
        p = _late_probability(ctx, inst_row, bank_code, inst.auto_renewal, len(inst.discrepancies))
        late = rnd.random() < p
        z = ctx.lateness[inst_row.id]
        delay = (max(4, round(rnd.gauss(35 + 25 * z, 30))) if late
                 else -max(4, round(rnd.gauss(40 - 18 * z, 20))))
        arrival = maturity + timedelta(days=delay)
        if arrival > today():
            break
        prev = inst
        issue = arrival - timedelta(days=rnd.randint(0, 9))
        if rnd.random() < 0.15:
            bank_code = rnd.choices(list(D.BANK_WEIGHTS), list(D.BANK_WEIGHTS.values()))[0]
            if bank_code == "DCNB":
                bank_code = "BHRT"
    return out


def _release(db: Session, ctx: Ctx, inst: Instrument, when: datetime, reason: str) -> None:
    rnd = ctx.rnd
    now = utcnow()
    requester = ctx.inst_users.get(inst.institution_id) or inst.assigned_officer or ctx.officers[0]
    r = release.request(db, inst, requester, reason, "Programme closed with approval; no students on roll."
                        if reason == ReleaseReason.CLOSURE else "Holding period completed.", at=when)
    t = when + timedelta(days=rnd.randint(2, 10))
    if t > now:
        return
    officer = inst.assigned_officer or ctx.officers[0]
    checklist = {k: {"ok": True, "note": "Checked."} for k, _ in release.CONDITIONS}
    release.recommend(db, r, officer, checklist, "All conditions met.", at=t)
    t2 = t + timedelta(days=rnd.randint(2, 12))
    if t2 > now:
        return
    release.decide(db, r, ctx.ca, True, "Approved.", at=t2)
    t3 = t2 + timedelta(days=rnd.randint(1, 8))
    if t3 > now:
        return
    release.execute(db, r, ctx.accounts, None, at=t3)


def _history(db: Session, ctx: Ctx, institutions: list[Institution], log) -> None:
    rnd = ctx.rnd
    total = 0
    for k, row in enumerate(institutions):
        if rnd.random() < 0.78:
            est = max(row.established_year or 2010, 2014)
            start = date(min(est, 2021), rnd.randint(4, 9), rnd.randint(1, 28)) + timedelta(days=rnd.randint(0, 900))
            total += len(chain(db, ctx, row, "NEW_INSTITUTION", min(start, today() - timedelta(days=40))))
        if rnd.random() < 0.32:
            start = date(rnd.randint(2017, 2025), rnd.randint(4, 8), rnd.randint(1, 28))
            if start < today() - timedelta(days=20):
                total += len(chain(db, ctx, row, "NEW_PROGRAMME", start))
        if rnd.random() < 0.16:
            start = date(rnd.randint(2018, 2025), rnd.randint(4, 8), rnd.randint(1, 28))
            if start < today() - timedelta(days=20):
                total += len(chain(db, ctx, row, "INTAKE_INCREASE", start))
        if k % 100 == 99:
            db.flush()
            log(f"  {k + 1} institutions, {total} instruments")


# ---------------------------------------------------------------- planted scenarios


def _find(db: Session, name: str, city: str) -> Institution:
    return db.scalar(select(Institution).where(Institution.name == name, Institution.city == city))


def _clear_planted(db: Session, row: Institution) -> None:
    """Planted institutions get hand-written histories instead of random ones."""
    for inst in db.scalars(select(Instrument).where(Instrument.institution_id == row.id)):
        db.delete(inst)
    db.flush()


def _held(db: Session, ctx: Ctx, row: Institution, *, purpose="NEW_INSTITUTION", bank="BHRT", issue: date,
          tenure=60, maturity: date | None = None, bank_truth="same", amount=None, auto_renewal=False,
          fdr_number=None) -> Instrument:
    inst = lodge(db, ctx, row, purpose=purpose, approval_year=f"{issue.year}-{(issue.year + 1) % 100:02d}",
                 bank_code=bank, issue=issue, tenure_months=tenure, maturity=maturity,
                 submitted=_at(issue + timedelta(days=3), ctx.rnd), bank_truth=bank_truth, amount=amount,
                 auto_renewal=auto_renewal, fdr_number=fdr_number)
    process(db, ctx, inst)
    return inst


def _planted(db: Session, ctx: Ctx) -> dict[str, str]:
    rnd = ctx.rnd
    t = today()
    notes: dict[str, str] = {}
    rows = {(n, c): _find(db, n, c) for n, _s, c, *_ in PLANTED}
    for row in rows.values():
        _clear_planted(db, row)
    kit, kcp = rows[("Kadamb Institute of Technology", "Nashik")], rows[("Kadamb College of Pharmacy", "Nashik")]
    udaan = rows[("Udaan Institute of Management", "Lucknow")]
    tap_v, tap_vj = rows[("Tapasya College of Engineering", "Visakhapatnam")], rows[("Tapasya College of Engineering", "Vijayawada")]
    vidya = rows[("Shri Vidyadeep College of Engineering", "Pune")]
    sapt = rows[("Saptarishi Polytechnic", "Ludhiana")]
    nach = rows[("Nachiketa Institute of Engineering & Technology", "Jaipur")]
    ramdas = rows[("Late Shri Ramdas Kulkarni Memorial College of Engineering", "Belagavi")]
    medhavi = rows[("Medhavi Institute of Management Studies", "Hyderabad")]
    jagriti = rows[("Jagriti College of Pharmacy", "Ahmedabad")]
    pragyan = rows[("Pragyan Institute of Technology", "Bhubaneswar")]

    # 1. Kadamb Nashik: the institution's own view. Main FDR matures in 26 days; renewal not yet lodged.
    k1 = _held(db, ctx, kit, issue=t - relativedelta(months=60) + timedelta(days=26), bank="BHRT",
               fdr_number="40027713518")
    k2 = _held(db, ctx, kit, purpose="NEW_PROGRAMME", bank="BHRT", issue=t - timedelta(days=400), tenure=36,
               fdr_number="40031184602")
    notes["Institution view (renewal due)"] = f"kadamb@nidhi.test: {k1.ref_no} matures {k1.maturity_date:%d %b %Y}"
    notes["Kadamb second FDR"] = k2.ref_no

    # 2. Kadamb College of Pharmacy: clean renewal lodged, verified, ready for the officer to accept.
    old = _held(db, ctx, kcp, issue=t - relativedelta(months=60) + timedelta(days=12), bank="UNKB", tenure=60)
    new = lodge(db, ctx, kcp, purpose="NEW_INSTITUTION", approval_year="2026-27", bank_code="UNKB",
                issue=t - timedelta(days=4), tenure_months=60, submitted=_at(t - timedelta(days=3), rnd), replaces=old)
    process(db, ctx, new, accept=False)
    notes["Ready to accept (clean renewal)"] = f"{new.ref_no} replaces {old.ref_no}"

    # 3. Tapasya Visakhapatnam lodges the very FDR already lodged by Tapasya Vijayawada.
    genuine = _held(db, ctx, tap_vj, bank="VNDB", issue=t - timedelta(days=500), fdr_number="VN24417735")
    dup = lodge(db, ctx, tap_v, purpose="NEW_PROGRAMME", approval_year="2026-27", bank_code="VNDB",
                issue=genuine.issue_date, tenure_months=36, submitted=_at(t - timedelta(days=2), rnd),
                fdr_number="VN24417735", amount=genuine.amount, depositor="Tapasya Education Society",
                ifsc=genuine.ifsc, bank_truth="missing", maturity=genuine.maturity_date)
    process(db, ctx, dup, accept=False)
    notes["Duplicate FDR (fraud signal)"] = f"{dup.ref_no} reuses FDR of {genuine.ref_no}"

    # 4. Udaan Lucknow: renewed late three times; current FDR matures in 41 days.
    issue = date(2014, 6, 10)
    prev = None
    for gen, delay in enumerate([62, 48, 95]):
        inst = lodge(db, ctx, udaan, purpose="NEW_PROGRAMME", approval_year=f"{issue.year}-{(issue.year + 1) % 100:02d}",
                     bank_code="SNDB", issue=issue, tenure_months=36, submitted=_at(issue + timedelta(days=5), rnd),
                     replaces=prev, auto_renewal=False)
        process(db, ctx, inst)
        prev = inst
        issue = inst.maturity_date + timedelta(days=delay)
    last = lodge(db, ctx, udaan, purpose="NEW_PROGRAMME", approval_year="2023-24", bank_code="SNDB",
                 issue=t - relativedelta(months=36) + timedelta(days=41), tenure_months=36,
                 submitted=_at(t - relativedelta(months=36) + timedelta(days=46), rnd), replaces=prev, auto_renewal=False)
    process(db, ctx, last)
    notes["Likely to renew late"] = f"{last.ref_no} (Udaan, renewed late 3 times)"

    # 5. Saptarishi Ludhiana: accepted FDR that the bank now reports closed prematurely.
    s1 = _held(db, ctx, sapt, bank="HMLB", issue=t - timedelta(days=420))
    # Accepted months ago; since then the FDR was closed at the branch without AICTE's consent.
    for v in s1.verifications:
        v.requested_at = v.responded_at = _at(t - timedelta(days=200), rnd)
    rec = db.scalar(select(BankRecord).where(BankRecord.bank_id == s1.bank_id, BankRecord.fdr_number == s1.fdr_number))
    rec.status, rec.closed_on, rec.lien_holder = "CLOSED", t - timedelta(days=58), None
    notes["Bank reports FDR closed"] = f"{s1.ref_no} (periodic re-confirmation)"

    # 6. Nachiketa Jaipur: matured 52 days ago and not renewed (escalated to the competent authority).
    n1 = _held(db, ctx, nach, bank="KVRB", issue=t - relativedelta(months=36) - timedelta(days=52), tenure=36,
               purpose="NEW_PROGRAMME")
    notes["Matured, unrenewed, escalated"] = n1.ref_no

    # 7. Medhavi Hyderabad: the uploaded document shows less than declared (altered amount).
    m1 = lodge(db, ctx, medhavi, purpose="NEW_PROGRAMME", approval_year="2026-27", bank_code="NRMB",
               issue=t - timedelta(days=9), tenure_months=36, submitted=_at(t - timedelta(days=6), rnd),
               amount=500_000, doc_overrides={"amount": 50_000})
    process(db, ctx, m1, accept=False)
    notes["Document differs from declaration"] = m1.ref_no

    # 8. Ramdas Kulkarni Belagavi: no lien, too short and short of the amount.
    r1 = lodge(db, ctx, ramdas, purpose="NEW_PROGRAMME", approval_year="2026-27", bank_code="SHYB",
               issue=t - timedelta(days=12), tenure_months=24, submitted=_at(t - timedelta(days=10), rnd),
               amount=400_000, lien=None)
    process(db, ctx, r1, accept=False, stop_before_verify=True)
    notes["Several discrepancies"] = r1.ref_no

    # 9. Jagriti Ahmedabad: the bank has no such FDR.
    j1 = lodge(db, ctx, jagriti, purpose="INTAKE_INCREASE", approval_year="2026-27", bank_code="TPTB",
               issue=t - timedelta(days=15), tenure_months=36, submitted=_at(t - timedelta(days=5), rnd),
               bank_truth="missing")
    process(db, ctx, j1, accept=False)
    notes["Bank has no record"] = j1.ref_no

    # 10. Pragyan Bhubaneswar: depositor is a company, not the institution or its society.
    p1 = lodge(db, ctx, pragyan, purpose="INTAKE_INCREASE", approval_year="2026-27", bank_code="BHRT",
               issue=t - timedelta(days=7), tenure_months=36, submitted=_at(t - timedelta(days=4), rnd),
               depositor="Prerana Infra Builders Pvt Ltd")
    process(db, ctx, p1, accept=False)
    notes["Depositor name mismatch"] = p1.ref_no

    # 11. Vidyadeep Pune: three releases at different stages.
    v1 = _held(db, ctx, vidya, purpose="NEW_PROGRAMME", bank="UNKB", issue=t - timedelta(days=700), tenure=36)
    r_req = release.request(db, v1, ctx.officers[1], ReleaseReason.CLOSURE,
                            "M.Tech (Structural) closed from 2026-27 with AICTE approval; no students on roll.",
                            at=_at(t - timedelta(days=3), rnd))
    v2 = _held(db, ctx, vidya, purpose="INTAKE_INCREASE", bank="UNKB", issue=t - timedelta(days=800), tenure=36)
    r_rec = release.request(db, v2, ctx.officers[1], ReleaseReason.APPROVAL_NOT_GRANTED,
                            "Increase in intake for B.Tech (CSE) not granted for 2026-27.", at=_at(t - timedelta(days=9), rnd))
    release.recommend(db, r_rec, v2.assigned_officer or ctx.officers[0],
                      {k: {"ok": True, "note": "Verified from Approval Bureau records."} for k, _ in release.CONDITIONS},
                      "Approval not granted; deposit no longer required.", at=_at(t - timedelta(days=6), rnd))
    v3_row = rows[("Kadamb College of Pharmacy", "Nashik")]
    v3 = _held(db, ctx, v3_row, purpose="INTAKE_INCREASE", bank="UNKB", issue=t - timedelta(days=900), tenure=36)
    r_app = release.request(db, v3, ctx.officers[2], ReleaseReason.PERIOD_COMPLETED, "Three-year holding period over.",
                            at=_at(t - timedelta(days=14), rnd))
    release.recommend(db, r_app, ctx.officers[2], {k: {"ok": True, "note": "Checked."} for k, _ in release.CONDITIONS},
                      "Recommended.", at=_at(t - timedelta(days=11), rnd))
    release.decide(db, r_app, ctx.ca, True, "Approved.", at=_at(t - timedelta(days=4), rnd))
    notes["Release: awaiting recommendation"] = v1.ref_no
    notes["Release: awaiting approval"] = v2.ref_no
    notes["Release: awaiting execution"] = v3.ref_no
    db.flush()
    return notes


# ---------------------------------------------------------------- samples for the live demo


def write_samples(db: Session, ctx: Ctx, out_dir: Path) -> list[Path]:
    """Specimen FDRs for the live demo: Kadamb's renewal (clean) and an altered copy."""
    out_dir.mkdir(parents=True, exist_ok=True)
    kit = _find(db, "Kadamb Institute of Technology", "Nashik")
    t = today()
    common = {"bank_name": "Bharat National Bank", "branch": "Nashik Station Road", "ifsc": "BHRT0004521",
              "issue_date": t, "maturity_date": t + relativedelta(months=60), "depositor": kit.society_name,
              "lien_holder": LIEN, "rate": 7.0, "style": 0}
    clean = out_dir / "kadamb_renewal_fdr.pdf"
    clean.write_bytes(draw_specimen(fdr_number="40045520917", amount=1_500_000, **common))
    altered = out_dir / "kadamb_renewal_fdr_altered.pdf"
    altered.write_bytes(draw_specimen(fdr_number="40045520917", amount=150_000, **common))
    # The bank knows the clean one.
    bank = ctx.banks["BHRT"]
    if not db.scalar(select(BankRecord).where(BankRecord.bank_id == bank.id, BankRecord.fdr_number == "40045520917")):
        db.add(BankRecord(bank_id=bank.id, fdr_number="40045520917", branch="Nashik Station Road", ifsc="BHRT0004521",
                          depositor_name=kit.society_name, amount=1_500_000, issue_date=t,
                          maturity_date=t + relativedelta(months=60), lien_holder=LIEN, status="LIVE"))
    return [clean, altered]


# ---------------------------------------------------------------- entry point


def seed(db: Session, *, n_institutions: int = 600, rnd_seed: int = 2026, samples_dir: Path | None = None,
         log=print) -> dict:
    from ..services import prediction
    from ..services.ledger import anchor
    from ..services.monitor import run_monitor

    if db.scalar(select(User.id).limit(1)):
        raise RuntimeError("Database already has data; reset it before seeding")
    rnd = random.Random(rnd_seed)
    invalidate_index()
    log("· master data")
    _master(db)
    log(f"· {n_institutions} institutions")
    institutions = _institutions(db, rnd, n_institutions)
    for inst in institutions[: len(PLANTED)]:
        db.add(InstitutionAlias(institution_id=inst.id, alias=inst.name, normalized=inst.normalized_name, source="MASTER"))
    db.flush()
    users = db.scalars(select(User)).all()
    by_handle = {u.email.split("@")[0]: u for u in users}
    upload = Path(get_settings().upload_dir)
    upload.mkdir(parents=True, exist_ok=True)
    ctx = Ctx(rnd=rnd, today=today(), banks={b.code: b for b in db.scalars(select(Bank))},
              officers=[u for u in users if u.role == Role.RB_OFFICER], head=by_handle["rb.head"], ca=by_handle["ms"],
              accounts=by_handle["accounts"], upload_dir=upload)
    pw = by_handle["ms"].password_hash
    for (name, _st, city, *_rest, handle) in PLANTED:
        if handle:
            row = _find(db, name, city)
            u = User(email=f"{handle}@nidhi.test", full_name=f"Principal, {row.name}", designation="Principal / Director",
                     role=Role.INSTITUTION, institution_id=row.id, password_hash=pw)
            db.add(u)
            db.flush()
            ctx.inst_users[row.id] = u
    banks, weights = list(D.BANK_WEIGHTS), list(D.BANK_WEIGHTS.values())
    for row in institutions:
        ctx.lateness[row.id] = rnd.gauss(0, 1)
        ctx.home_bank[row.id] = rnd.choices(banks, weights)[0]
    log("· a decade of deposits: lodged, verified, accepted, renewed or released")
    _history(db, ctx, institutions[len(PLANTED):], log)
    db.commit()
    log("· demo scenarios")
    notes = _planted(db, ctx)
    db.commit()
    log("· late-renewal model")
    prediction.reset()
    model = prediction.train(db)
    db.commit()
    log(f"  AUC {model.get('auc')} on {model.get('holdout_instruments')} held-out instruments")
    log("· maturity monitor, periodic bank re-confirmation, risk scores and ledger checkpoint")
    prediction.score_held(db)
    stats = run_monitor(db)
    anchor(db, note="Checkpoint after loading the demonstration dataset")
    if samples_dir:
        paths = write_samples(db, ctx, samples_dir)
        log("· sample FDRs for the demo: " + ", ".join(str(p) for p in paths))
    db.commit()
    from ..services.evaluation import evaluate_and_store

    log("· measuring the checks and the document reader on fresh test cases")
    ev = evaluate_and_store(db, n_scans=45 if n_institutions >= 300 else 6)
    db.commit()
    log(f"  checks: precision {ev['checks']['precision']}, recall {ev['checks']['recall']}; "
        f"reader: {ev['reader']['field_accuracy']} of fields"
        + (f"; scanned copies by OCR: {ev['scanned']['field_accuracy']}" if ev.get("scanned") else "; OCR not installed"))
    totals = {
        "institutions": len(institutions),
        "instruments": db.query(Instrument).count(),
        "held": db.query(Instrument).filter(Instrument.status.in_(["ACTIVE", "EXPIRING", "MATURED", "RELEASE_REQUESTED"])).count(),
        "alerts": db.query(Alert).count(),
        "instrument_events": db.query(InstrumentEvent).count(),
        "monitor": stats,
        "renewal_model": {k: model.get(k) for k in ("auc", "average_precision", "holdout_instruments", "base_rate")},
    }
    return {"totals": totals, "scenarios": notes}
