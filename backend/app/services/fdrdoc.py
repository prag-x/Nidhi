"""Reading FDR documents, and drawing the synthetic specimens used in the demo.

`read_fdr` pulls the FDR number, amount, dates, depositor and lien from a PDF's text layer, offline. A scanned PDF
or a photo (PNG/JPG) has no text layer, so it is read with Tesseract OCR on this server instead. It copes with
the different wordings banks use ("FDR No." / "Deposit No." / "Receipt No.", "Principal" / "Deposit Amount") and
date formats, and ignores look-alike figures such as the maturity value or interest rate.

`draw_specimen` produces a deliberately plain, clearly watermarked specimen for the demo dataset. The banks in the
demo are fictional; nothing here imitates a real bank's stationery.
"""

from __future__ import annotations

import io
import re
from datetime import date, datetime

FIELDS = ("fdr_number", "amount", "issue_date", "maturity_date", "depositor_name", "lien_holder")

LABELS = {
    "fdr_number": [r"fdr\s*no\.?", r"deposit\s*no\.?", r"receipt\s*no\.?", r"account\s*/\s*receipt\s*no\.?",
                   r"term\s*deposit\s*no\.?"],
    "amount": [r"deposit\s*amount", r"principal(?:\s*amount)?", r"amount\s*of\s*deposit", r"amount\s*\(inr\)",
               r"amount\s*\(rs\.?\)"],
    "issue_date": [r"date\s*of\s*deposit", r"value\s*date", r"opened\s*on", r"date\s*of\s*issue", r"issue\s*date"],
    "maturity_date": [r"date\s*of\s*maturity", r"maturity\s*date", r"due\s*on", r"due\s*date"],
    "depositor_name": [r"name\s*of\s*depositor\(?s?\)?", r"customer\s*name", r"in\s*the\s*name\s*of",
                       r"depositor"],
    "lien_holder": [r"lien\s*marked\s*in\s*favou?r\s*of", r"pledged\s*to", r"under\s*lien\s*to",
                    r"lien\s*in\s*favou?r\s*of"],
}
DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d-%b-%Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%d")


def parse_amount(text: str) -> float | None:
    m = re.search(r"(?:rs\.?|inr|₹)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", text, re.I)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_date(text: str) -> date | None:
    text = text.strip().rstrip(".")
    m = re.search(r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}|\d{1,2}[\- ][A-Za-z]{3,9}[\- ]\d{4}|\d{4}-\d{2}-\d{2})", text)
    if not m:
        return None
    raw = m.group(1)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages[:3])


def read_text(text: str) -> tuple[dict, float]:
    """Extract fields from the text of an FDR. Returns (values, share of fields found)."""
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    found: dict = {}
    for field, patterns in LABELS.items():
        for i, ln in enumerate(lines):
            hit = None
            for pat in patterns:
                m = re.search(rf"\b{pat}(?:\s*\([^)]*\))?\s*[:\-]?\s*(.*)$", ln, re.I)
                if m:
                    hit = m.group(1).strip() or (lines[i + 1] if i + 1 < len(lines) else "")
                    break
            if hit is None:
                continue
            if field == "amount":
                if re.search(r"maturity\s*value|interest", ln, re.I):
                    continue
                value = parse_amount(hit)
            elif field in ("issue_date", "maturity_date"):
                value = parse_date(hit)
                value = value.isoformat() if value else None
            elif field == "fdr_number":
                m2 = re.search(r"[A-Z0-9][A-Z0-9/\-]{5,}", hit, re.I)
                value = m2.group(0).upper() if m2 else None
            else:
                value = re.split(r"\s{2,}|\s+(?:interest|rate|tenure)\b", hit, flags=re.I)[0].strip(" .:") or None
            if value not in (None, ""):
                found[field] = value
                break
    confidence = round(len(found) / len(FIELDS), 2)
    # The IFSC, when printed, identifies the bank and branch; it helps pre-fill the form but is not scored.
    m = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", text)
    if m:
        found["ifsc"] = m.group(1)
    return found, confidence


def ocr_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001 - library or binary missing: OCR is simply unavailable
        return False


def _ocr_image(img) -> str:
    import pytesseract

    img = img.convert("L")
    if img.width < 1600:  # small photos read better enlarged
        scale = 1600 / img.width
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    return pytesseract.image_to_string(img, config="--psm 6")


def ocr_text(data: bytes, kind: str) -> str:
    """Text of a scanned PDF (first two pages) or a photo, by OCR. Empty if OCR is not installed."""
    if not ocr_available():
        return ""
    from PIL import Image

    if kind == "pdf":
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(data)
        pages = [doc[i].render(scale=300 / 72).to_pil() for i in range(min(2, len(doc)))]
    else:
        pages = [Image.open(io.BytesIO(data))]
    return "\n".join(_ocr_image(p) for p in pages)


def read_fdr(data: bytes, ext: str = ".pdf") -> tuple[dict, float]:
    """Read the FDR's fields: from the PDF text layer if it has one, otherwise by OCR."""
    ext = ext.lower()
    text = ""
    if ext == ".pdf":
        try:
            text = pdf_text(data)
        except ImportError:
            raise  # a missing PDF library is a deployment fault, not an unreadable document
        except Exception:  # noqa: BLE001 - damaged PDF: try OCR below
            text = ""
    if len(text.strip()) < 40:  # scanned PDF or a photo
        try:
            text = ocr_text(data, "pdf" if ext == ".pdf" else "image")
        except Exception:  # noqa: BLE001 - unreadable image: nothing extracted, the officer reads it
            return {}, 0.0
    if not text.strip():
        return {}, 0.0
    return read_text(text)


# ---------------------------------------------------------------- specimens for the demo

STYLES = [
    {"title": "FIXED DEPOSIT RECEIPT", "fdr": "FDR No.", "amount": "Deposit Amount", "issue": "Date of Deposit",
     "maturity": "Date of Maturity", "name": "Name of Depositor(s)", "lien": "Lien marked in favour of",
     "datefmt": "%d/%m/%Y", "amtfmt": "rs"},
    {"title": "TERM DEPOSIT ADVICE", "fdr": "Account/Receipt No", "amount": "Principal (Rs.)", "issue": "Value Date",
     "maturity": "Maturity Date", "name": "Customer Name", "lien": "Pledged to", "datefmt": "%d-%b-%Y",
     "amtfmt": "plain"},
    {"title": "FD RECEIPT", "fdr": "Deposit No", "amount": "Amount (INR)", "issue": "Opened On", "maturity": "Due On",
     "name": "In the name of", "lien": "Under lien to", "datefmt": "%d.%m.%Y", "amtfmt": "inr"},
]


def indian_digits(n: float) -> str:
    s = f"{n:,.2f}"
    whole, frac = s.split(".")
    whole = whole.replace(",", "")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts) + "," + tail
    return f"{whole}.{frac}"


def draw_specimen(*, bank_name: str, branch: str, ifsc: str, fdr_number: str, amount: float, issue_date: date,
                  maturity_date: date, depositor: str, lien_holder: str | None, rate: float, style: int = 0) -> bytes:
    from reportlab.lib.colors import Color, HexColor
    from reportlab.lib.pagesizes import A5, landscape
    from reportlab.pdfgen import canvas

    st = STYLES[style % len(STYLES)]
    buf = io.BytesIO()
    w, h = landscape(A5)
    c = canvas.Canvas(buf, pagesize=(w, h))
    c.setTitle(f"Specimen FDR {fdr_number}")
    c.setStrokeColor(HexColor("#334155"))
    c.rect(18, 18, w - 36, h - 36)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(34, h - 50, bank_name)
    c.setFont("Helvetica", 9)
    c.drawString(34, h - 64, f"Branch: {branch}    IFSC: {ifsc}")
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(w - 34, h - 50, st["title"])

    years = max(1, round((maturity_date - issue_date).days / 365.25))
    maturity_value = amount * (1 + rate / 100) ** years
    amt = indian_digits(amount)
    amount_text = {"rs": f"Rs. {amt}", "plain": amt, "inr": f"INR {amount:.2f}"}[st["amtfmt"]]
    rows = [
        (st["fdr"], fdr_number),
        (st["name"], depositor),
        (st["amount"], amount_text),
        (st["issue"], issue_date.strftime(st["datefmt"])),
        (st["maturity"], maturity_date.strftime(st["datefmt"])),
        ("Rate of interest", f"{rate:.2f}% p.a."),
        ("Maturity value", f"Rs. {indian_digits(maturity_value)}"),
    ]
    if lien_holder:
        rows.append((st["lien"], lien_holder))
    y = h - 100
    for label, value in rows:
        c.setFont("Helvetica", 10)
        c.drawString(40, y, f"{label}:")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(210, y, str(value))
        y -= 20
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 40, "Subject to the terms and conditions of the deposit scheme. Not transferable.")
    # Watermark: this is a synthetic specimen, not a bank document.
    c.saveState()
    c.setFillColor(Color(0.85, 0.1, 0.1, alpha=0.18))
    c.setFont("Helvetica-Bold", 30)
    c.translate(w / 2, h / 2)
    c.rotate(18)
    c.drawCentredString(0, 0, "SYNTHETIC SPECIMEN - NOT A BANK DOCUMENT")
    c.restoreState()
    c.showPage()
    c.save()
    return buf.getvalue()
