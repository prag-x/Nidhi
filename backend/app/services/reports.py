"""Management reports: Bureau/Cell-wise, region-wise, institution-wise, ageing, performance, overlaps.

Each report is built once as a table (columns + rows + totals) and rendered as JSON for the UI,
or exported to Excel, PDF or CSV with the same numbers.
"""

from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import local_date, today, utcnow
from ..enums import HELD_STATUSES, PENDING_SCRUTINY, DiscrepancyStatus, ReleaseStatus, Status
from ..models import Bank, Discrepancy, Institution, Instrument, Region, ReleaseRequest

@dataclass
class Column:
    key: str
    label: str
    kind: str = "text"  # text | int | pct | float | date

    def as_dict(self):
        return {"key": self.key, "label": self.label, "kind": self.kind}


@dataclass
class Report:
    key: str
    title: str
    subtitle: str
    columns: list[Column]
    rows: list[dict]
    totals: dict | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self):
        return {
            "key": self.key, "title": self.title, "subtitle": self.subtitle,
            "columns": [c.as_dict() for c in self.columns], "rows": self.rows, "totals": self.totals,
            "notes": self.notes, "generated_at": utcnow().isoformat(),
        }


@dataclass
class Filters:
    date_from: date
    date_to: date
    region_id: int | None = None
    bank_id: int | None = None
    institution_id: int | None = None

    @classmethod
    def build(cls, date_from=None, date_to=None, **kw) -> Filters:
        to = date_to or today()
        return cls(date_from=date_from or (to - timedelta(days=365)), date_to=to, **kw)


def _pct(num: float, den: float) -> float | None:
    return round(100.0 * num / den, 1) if den else None


def _median(values) -> float | None:
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    m = len(v) // 2
    return float(v[m]) if len(v) % 2 else (v[m - 1] + v[m]) / 2


def _instruments(db: Session, f: Filters) -> list[Instrument]:
    q = select(Instrument).options(selectinload(Instrument.institution), selectinload(Instrument.bank))
    if f.region_id:
        q = q.where(Instrument.institution_id.in_(select(Institution.id).where(Institution.region_id == f.region_id)))
    if f.bank_id:
        q = q.where(Instrument.bank_id == f.bank_id)
    if f.institution_id:
        q = q.where(Instrument.institution_id == f.institution_id)
    return db.scalars(q).all()


def _scope(db: Session, f: Filters) -> str:
    parts = []
    if f.region_id:
        r = db.get(Region, f.region_id)
        parts.append(r.name if r else "")
    if f.bank_id:
        b = db.get(Bank, f.bank_id)
        parts.append(b.name if b else "")
    return " · ".join(p for p in parts if p) or "All Regional Offices and banks"


def _successors(items: list[Instrument]) -> set[int]:
    return {x.replaces_id for x in items if x.replaces_id and x.status != Status.REJECTED}


def lakh(x: float) -> float:
    return round(x / 1e5, 2)


def status_report(db: Session, f: Filters) -> Report:
    from .instruments import STATUS_LABELS

    items = _instruments(db, f)
    by = defaultdict(lambda: [0, 0.0])
    for x in items:
        by[x.status][0] += 1
        by[x.status][1] += x.amount
    rows = [{"status": STATUS_LABELS[s], "count": by[s][0], "amount_lakh": lakh(by[s][1])} for s in Status if by[s][0]]
    cols = [Column("status", "Status"), Column("count", "Instruments", "int"), Column("amount_lakh", "Amount (Rs lakh)", "float")]
    return Report("status", "Instruments by status", _scope(db, f), cols, rows, _totals(rows, cols))


def maturity_report(db: Session, f: Filters) -> Report:
    items = _instruments(db, f)
    succ = _successors(items)
    start = today().replace(day=1)
    months = [(start + timedelta(days=32 * i)).replace(day=1) for i in range(12)]
    rows = []
    for m in months:
        nxt = (m + timedelta(days=32)).replace(day=1)
        due = [x for x in items if x.status in HELD_STATUSES and m <= x.maturity_date < nxt]
        renewed = [x for x in due if x.id in succ]
        rows.append({"month": m.strftime("%b %Y"), "maturing": len(due), "amount_lakh": lakh(sum(x.amount for x in due)),
                     "renewal_lodged": len(renewed), "not_yet": len(due) - len(renewed),
                     "high_risk": sum(1 for x in due if (x.renewal_risk or 0) >= 0.7 and x.id not in succ)})
    cols = [Column("month", "Month"), Column("maturing", "Maturing", "int"), Column("amount_lakh", "Amount (Rs lakh)", "float"),
            Column("renewal_lodged", "Renewal lodged", "int"), Column("not_yet", "Not yet lodged", "int"),
            Column("high_risk", "Likely late", "int")]
    overdue = [x for x in items if x.status == Status.MATURED and x.id not in succ]
    return Report("maturity", "Maturity calendar (next 12 months)", _scope(db, f), cols, rows, _totals(rows, cols),
                  notes=[f"{len(overdue)} instrument(s) have already matured without a replacement."])


def pending_report(db: Session, f: Filters) -> Report:
    items = [x for x in _instruments(db, f) if x.status in PENDING_SCRUTINY]
    rows = []
    for x in sorted(items, key=lambda x: x.submitted_at):
        rows.append({"ref_no": x.ref_no, "institution": f"{x.institution.name}, {x.institution.city}",
                     "bank": x.bank.short_name if x.bank else (x.bank_name_raw or "—"), "fdr": x.fdr_number,
                     "amount_lakh": lakh(x.amount), "age": (today() - local_date(x.submitted_at)).days,
                     "verification": x.verification_status.title(), "discrepancies": x.open_discrepancies,
                     "status": x.status.replace("_", " ").title()})
    cols = [Column("ref_no", "Ref"), Column("institution", "Institution"), Column("bank", "Bank"), Column("fdr", "FDR"),
            Column("amount_lakh", "Rs lakh", "float"), Column("age", "Days pending", "int"),
            Column("verification", "Bank"), Column("discrepancies", "Open discrepancies", "int"), Column("status", "Status")]
    return Report("pending", "Pending scrutiny and verification", _scope(db, f), cols, rows)


def discrepancy_report(db: Session, f: Filters) -> Report:
    from .checks import RULES

    ids = {x.id for x in _instruments(db, f)}
    ds = [d for d in db.scalars(select(Discrepancy).options(selectinload(Discrepancy.instrument))) if d.instrument_id in ids]
    by = defaultdict(lambda: {"open": 0, "resolved": 0, "waived": 0, "insts": set()})
    for d in ds:
        k = by[d.code]
        k[{"OPEN": "open", "RESOLVED": "resolved", "WAIVED": "waived"}[d.status]] += 1
        if d.status == DiscrepancyStatus.OPEN:
            k["insts"].add(d.instrument.institution_id)
    rows = [{"rule": RULES.get(code, (code,))[0], "severity": RULES.get(code, (None, "MEDIUM"))[1].title(),
             "open": v["open"], "resolved": v["resolved"], "waived": v["waived"], "institutions": len(v["insts"])}
            for code, v in sorted(by.items(), key=lambda kv: -kv[1]["open"])]
    cols = [Column("rule", "Check"), Column("severity", "Severity"), Column("open", "Open", "int"),
            Column("resolved", "Resolved", "int"), Column("waived", "Waived", "int"),
            Column("institutions", "Institutions with open items", "int")]
    return Report("discrepancies", "Discrepancies by check", _scope(db, f), cols, rows, _totals(rows, cols))


def bank_report(db: Session, f: Filters) -> Report:
    items = _instruments(db, f)
    rows = []
    for bank in db.scalars(select(Bank).order_by(Bank.name)):
        mine = [x for x in items if x.bank_id == bank.id]
        held = [x for x in mine if x.status in HELD_STATUSES]
        if not mine:
            continue
        turn = [(local_date(x.verified_at) - local_date(x.submitted_at)).days for x in mine if x.verified_at]
        rows.append({"bank": bank.name, "channel": "Online" if bank.verify_channel == "GATEWAY" else "Letter",
                     "held": len(held), "amount_lakh": lakh(sum(x.amount for x in held)),
                     "mismatch": sum(1 for x in mine if x.verification_status in ("MISMATCH", "NOT_FOUND")),
                     "median_days": _median(turn)})
    cols = [Column("bank", "Bank"), Column("channel", "Verification"), Column("held", "Held", "int"),
            Column("amount_lakh", "Rs lakh", "float"), Column("mismatch", "Mismatch / not found", "int"),
            Column("median_days", "Median days to verify", "float")]
    return Report("banks", "Banks: holdings and verification", _scope(db, f), cols, rows, _totals(rows, cols))


def region_report(db: Session, f: Filters) -> Report:
    items = _instruments(db, f)
    succ = _successors(items)
    rows = []
    for r in db.scalars(select(Region).order_by(Region.name)):
        mine = [x for x in items if x.institution.region_id == r.id]
        held = [x for x in mine if x.status in HELD_STATUSES]
        rows.append({"region": r.name, "held": len(held), "amount_lakh": lakh(sum(x.amount for x in held)),
                     "expiring": sum(1 for x in held if 0 <= (x.maturity_date - today()).days <= 90 and x.id not in succ),
                     "matured_unrenewed": sum(1 for x in held if x.status == Status.MATURED and x.id not in succ),
                     "pending": sum(1 for x in mine if x.status in PENDING_SCRUTINY),
                     "discrepancies": sum(x.open_discrepancies for x in mine)})
    cols = [Column("region", "Regional Office"), Column("held", "Held", "int"), Column("amount_lakh", "Rs lakh", "float"),
            Column("expiring", "Expiring in 90 days", "int"), Column("matured_unrenewed", "Matured, unrenewed", "int"),
            Column("pending", "Pending scrutiny", "int"), Column("discrepancies", "Open discrepancies", "int")]
    return Report("regions", "Regional Offices", _scope(db, f), cols, rows, _totals(rows, cols))


def release_report(db: Session, f: Filters) -> Report:
    from .release import REASON_LABELS

    ids = {x.id for x in _instruments(db, f)}
    rs = [r for r in db.scalars(select(ReleaseRequest).options(selectinload(ReleaseRequest.instrument)))
          if r.instrument_id in ids and f.date_from <= local_date(r.requested_at) <= f.date_to]
    rows = []
    for r in sorted(rs, key=lambda r: r.requested_at, reverse=True):
        x = r.instrument
        done = (local_date(r.executed_at) - local_date(r.requested_at)).days if r.executed_at else None
        rows.append({"ref_no": x.ref_no, "institution": f"{x.institution.name}, {x.institution.city}",
                     "reason": REASON_LABELS.get(r.reason, r.reason), "amount_lakh": lakh(x.amount),
                     "requested": local_date(r.requested_at).isoformat(), "status": r.status.title(), "days": done})
    cols = [Column("ref_no", "Ref"), Column("institution", "Institution"), Column("reason", "Reason"),
            Column("amount_lakh", "Rs lakh", "float"), Column("requested", "Requested"), Column("status", "Status"),
            Column("days", "Days to complete", "int")]
    executed = [r for r in rs if r.status == ReleaseStatus.EXECUTED]
    return Report("releases", "Release register", f"{f.date_from:%d %b %Y} to {f.date_to:%d %b %Y}", cols, rows,
                  notes=[f"{len(executed)} completed; median {(_median([(local_date(r.executed_at) - local_date(r.requested_at)).days for r in executed]) or 0):.0f} days from request to lien release."])


def performance_report(db: Session, f: Filters) -> Report:
    items = _instruments(db, f)
    by_month: dict[str, dict] = defaultdict(lambda: {"lodged": 0, "accepted": 0, "turn": [], "on_time": 0, "late": 0,
                                                     "released": 0})
    for x in items:
        sub = local_date(x.submitted_at)
        if f.date_from <= sub <= f.date_to:
            by_month[sub.strftime("%Y-%m")]["lodged"] += 1
        if x.accepted_at and f.date_from <= local_date(x.accepted_at) <= f.date_to:
            m = by_month[local_date(x.accepted_at).strftime("%Y-%m")]
            m["accepted"] += 1
            m["turn"].append((local_date(x.accepted_at) - sub).days)
        if x.renewed_late is not None and x.closed_at and f.date_from <= local_date(x.closed_at) <= f.date_to:
            by_month[local_date(x.closed_at).strftime("%Y-%m")]["late" if x.renewed_late else "on_time"] += 1
        if x.status == Status.RELEASED and x.closed_at and f.date_from <= local_date(x.closed_at) <= f.date_to:
            by_month[local_date(x.closed_at).strftime("%Y-%m")]["released"] += 1
    rows = []
    for key in sorted(by_month):
        m = by_month[key]
        rows.append({"month": datetime.strptime(key, "%Y-%m").strftime("%b %Y"), "lodged": m["lodged"],
                     "accepted": m["accepted"], "median_days": _median(m["turn"]),
                     "renewed_on_time": m["on_time"], "renewed_late": m["late"],
                     "on_time_rate": _pct(m["on_time"], m["on_time"] + m["late"]), "released": m["released"]})
    cols = [Column("month", "Month"), Column("lodged", "Lodged", "int"), Column("accepted", "Accepted", "int"),
            Column("median_days", "Median days to accept", "float"), Column("renewed_on_time", "Renewed on time", "int"),
            Column("renewed_late", "Renewed late", "int"), Column("on_time_rate", "On time", "pct"),
            Column("released", "Released", "int")]
    return Report("performance", "Monthly performance", f"{f.date_from:%d %b %Y} to {f.date_to:%d %b %Y}", cols, rows,
                  _totals(rows, cols))


def institution_history_report(db: Session, institution_id: int) -> Report:
    from .instruments import STATUS_LABELS

    inst = db.get(Institution, institution_id)
    items = sorted(_instruments(db, Filters.build(institution_id=institution_id)), key=lambda x: x.issue_date)
    rows = [{"ref_no": x.ref_no, "purpose": x.purpose.replace("_", " ").title(), "bank": x.bank.short_name if x.bank else "—",
             "fdr": x.fdr_number, "amount_lakh": lakh(x.amount), "issued": x.issue_date.isoformat(),
             "matures": x.maturity_date.isoformat(), "status": STATUS_LABELS.get(x.status, x.status),
             "late": "Yes" if x.renewed_late else ("No" if x.renewed_late is False else "")} for x in items]
    cols = [Column("ref_no", "Ref"), Column("purpose", "Purpose"), Column("bank", "Bank"), Column("fdr", "FDR"),
            Column("amount_lakh", "Rs lakh", "float"), Column("issued", "Issued"), Column("matures", "Matures"),
            Column("status", "Status"), Column("late", "Renewed late")]
    return Report("institution", f"Deposit history: {inst.name}, {inst.city}", f"AICTE PID {inst.aicte_pid}", cols, rows)


REPORTS = {
    "status": status_report, "maturity": maturity_report, "pending": pending_report,
    "discrepancies": discrepancy_report, "banks": bank_report, "regions": region_report,
    "releases": release_report, "performance": performance_report,
}


def _totals(rows: list[dict], cols: list[Column]) -> dict | None:
    if not rows:
        return None
    totals: dict = {cols[0].key: "Total"}
    for c in cols[1:]:
        if c.kind == "int":
            totals[c.key] = sum(r.get(c.key) or 0 for r in rows)
    return totals


# ---------------------------------------------------------------- exporters


def _fmt(value, kind: str) -> str:
    if value is None:
        return "—"
    if kind == "pct":
        return f"{value:.1f}%"
    if kind == "float":
        return f"{value:.1f}"
    return str(value)


FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def cell_safe(value):
    """Complaint text is typed by the public. Text that a spreadsheet would run as a formula
    (=HYPERLINK(...), +cmd, @SUM) is prefixed with an apostrophe so it shows as plain text."""
    if isinstance(value, str) and value.startswith(FORMULA_START):
        return "'" + value
    return value


def to_csv(report: Report) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([report.title])
    w.writerow([report.subtitle])
    w.writerow([c.label for c in report.columns])
    for row in report.rows + ([report.totals] if report.totals else []):
        w.writerow(["" if row.get(c.key) is None else cell_safe(row.get(c.key)) for c in report.columns])
    return buf.getvalue().encode("utf-8-sig")


def to_xlsx(report: Report, generated_by: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = report.key[:31]
    ws["A1"] = report.title
    ws["A1"].font = Font(bold=True, size=14, color="1F3A5F")
    ws["A2"] = report.subtitle
    ws["A3"] = f"Generated {utcnow().strftime('%d %b %Y %H:%M UTC')} by {generated_by} · Nidhi"
    ws["A2"].font = ws["A3"].font = Font(italic=True, size=9, color="555555")
    header_row = 5
    thin = Side(style="thin", color="D0D7E2")
    for i, col in enumerate(report.columns, start=1):
        cell = ws.cell(row=header_row, column=i, value=col.label)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3A5F")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        cell.border = Border(bottom=thin)
    body = report.rows + ([report.totals] if report.totals else [])
    for r_i, row in enumerate(body, start=header_row + 1):
        is_total = report.totals is not None and row is report.totals
        for c_i, col in enumerate(report.columns, start=1):
            value = cell_safe(row.get(col.key))
            cell = ws.cell(row=r_i, column=c_i, value=value / 100 if col.kind == "pct" and value is not None else value)
            if col.kind == "pct":
                cell.number_format = "0.0%"
            elif col.kind == "float":
                cell.number_format = "0.0"
            if is_total:
                cell.font = Font(bold=True)
                cell.fill = PatternFill("solid", fgColor="EEF2F7")
    for i, col in enumerate(report.columns, start=1):
        width = max([len(col.label)] + [len(_fmt(r.get(col.key), col.kind)) for r in body[:500]]) + 2
        ws.column_dimensions[get_column_letter(i)].width = min(max(width, 10), 60)
    ws.freeze_panes = ws.cell(row=header_row + 1, column=2)
    row = header_row + len(body) + 2
    for note in report.notes:
        ws.cell(row=row, column=1, value=note).font = Font(italic=True, size=9)
        row += 1
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def to_pdf(report: Report, generated_by: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    page = landscape(A4)
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=14 * mm,
                            bottomMargin=14 * mm, title=report.title, author="Nidhi")
    styles = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=styles["BodyText"], fontSize=7.5, leading=9)
    head = ParagraphStyle("head", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")
    story = [
        Paragraph(report.title, ParagraphStyle("t", parent=styles["Title"], fontSize=15, alignment=0,
                                               textColor=colors.HexColor("#1F3A5F"))),
        Paragraph(report.subtitle, ParagraphStyle("s", parent=styles["BodyText"], fontSize=8.5,
                                                  textColor=colors.HexColor("#555555"))),
        Spacer(1, 4 * mm),
    ]
    body = report.rows + ([report.totals] if report.totals else [])
    data = [[Paragraph(c.label, head) for c in report.columns]]
    for row in body:
        data.append([Paragraph(_fmt(row.get(c.key), c.kind).replace("&", "&amp;").replace("<", "&lt;"), cell)
                     for c in report.columns])
    if len(data) == 1:
        data.append([Paragraph("No records for the selected filters.", cell)] + [""] * (len(report.columns) - 1))
    avail = page[0] - 24 * mm
    weights = [3 if c.kind == "text" else 1.2 for c in report.columns]
    widths = [avail * w / sum(weights) for w in weights]
    table = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D0D7E2")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F8FB")]),
    ]
    if report.totals:
        style.append(("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), colors.HexColor("#E3E9F2")))
    table.setStyle(TableStyle(style))
    story.append(table)
    for note in report.notes:
        story += [Spacer(1, 3 * mm), Paragraph(note, ParagraphStyle("n", parent=cell, textColor=colors.HexColor("#555555")))]

    stamp = f"Generated {utcnow().strftime('%d %b %Y %H:%M UTC')} by {generated_by}"

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(12 * mm, 8 * mm, f"Nidhi · AICTE Security Deposit / FDR Management · {stamp}")
        canvas.drawRightString(page[0] - 12 * mm, 8 * mm, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
