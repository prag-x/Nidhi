"""Ask the portal: turn a plain question (English or Hindi) into instrument filters, on this server.

No language model is involved. The question is read with vocabularies built from the portal's own master data (banks,
regions, states, institutions) plus phrases for status, maturity, verification, discrepancies and amounts. Every part
that was understood is returned as a chip, so the official can see exactly how the question was read.
"""

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..matching.institutions import get_index
from ..models import Bank, Region, State

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
STATE_HI = {
    "महाराष्ट्र": "MH", "गोवा": "GA", "तमिलनाडु": "TN", "कर्नाटक": "KA", "केरल": "KL", "मध्य प्रदेश": "MP",
    "छत्तीसगढ़": "CG", "गुजरात": "GJ", "पंजाब": "PB", "हरियाणा": "HR", "हिमाचल": "HP", "जम्मू": "JK", "दिल्ली": "DL",
    "राजस्थान": "RJ", "उत्तर प्रदेश": "UP", "उत्तराखंड": "UK", "बिहार": "BR", "पश्चिम बंगाल": "WB", "ओडिशा": "OD",
    "झारखंड": "JH", "तेलंगाना": "TG", "आंध्र प्रदेश": "AP", "असम": "AS", "चंडीगढ़": "CH", "पुडुचेरी": "PY",
}
# (filter, value, english label, hindi label, phrases)
FLAGS = [
    ("matured_unrenewed", "true", "Matured, not renewed", "परिपक्व, नवीनीकरण नहीं",
     ["matured", "not renewed", "unrenewed", "overdue renewal", "lapsed", "परिपक्व", "नवीनीकरण नहीं", "समाप्त"]),
    ("at_risk", "true", "Likely to renew late", "देर से नवीनीकरण की संभावना",
     ["likely late", "likely to be late", "likely to renew late", "likely", "at risk", "renew late", "high risk", "देरी की संभावना", "जोखिम"]),
    ("discrepancy", "any", "With open discrepancies", "खुली विसंगतियाँ",
     ["discrepancy", "discrepancies", "mismatch", "mismatches", "flagged", "problem", "problems", "विसंगति",
      "विसंगतियाँ", "विसंगतियों"]),
    ("assigned", "unassigned", "No dealing officer", "बिना अधिकारी", ["unassigned", "no officer", "not assigned"]),
    ("assigned", "me", "Assigned to me", "मुझे सौंपे गए", ["my files", "assigned to me", "mine", "मेरे"]),
]
VERIFICATION = [
    ("REQUESTED", "Awaiting bank reply", "बैंक उत्तर की प्रतीक्षा",
     ["awaiting bank", "bank reply", "pending verification", "not verified", "unverified", "सत्यापन लंबित"]),
    ("NOT_FOUND", "Bank has no record", "बैंक में रिकॉर्ड नहीं", ["not found at bank", "bank has no record", "fake"]),
    ("CONFIRMED", "Confirmed by bank", "बैंक द्वारा पुष्टि", ["confirmed by bank", "bank confirmed", "verified"]),
]
STATUS = [
    ("RELEASE_REQUESTED", "Release requested", "रिलीज़ का अनुरोध", ["release requested", "release request", "refund request",
                                                                  "रिलीज़", "वापसी"]),
    ("RELEASED", "Released", "रिलीज़ किए गए", ["released", "refunded", "discharged"]),
    ("RENEWED", "Renewed", "नवीनीकृत", ["renewed", "replaced", "नवीनीकृत"]),
    ("PENDING", "Pending scrutiny", "जांच लंबित", ["pending scrutiny", "under scrutiny", "pending", "new submissions",
                                                   "लंबित", "जांच"]),
    ("HELD", "Held by AICTE", "AICTE के पास", ["held", "active", "live", "सक्रिय"]),
]
PURPOSE = [
    ("NEW_INSTITUTION", "New institution", "नया संस्थान", ["new institution", "new college", "नया संस्थान"]),
    ("NEW_PROGRAMME", "New programme", "नया पाठ्यक्रम", ["new programme", "new program", "new course", "नया पाठ्यक्रम"]),
    ("INTAKE_INCREASE", "Increase in intake", "प्रवेश क्षमता वृद्धि", ["intake increase", "increase in intake",
                                                                      "additional intake"]),
]
COUNT = ["how many", "number of", "count", "total", "कितने", "कितनी", "संख्या"]
STOP = {"the", "a", "an", "of", "in", "at", "on", "for", "with", "and", "to", "by", "from", "show", "me", "list", "all",
        "fdr", "fdrs", "deposit", "deposits", "instrument", "instruments", "security", "about", "which", "what", "how",
        "many", "are", "is", "there", "have", "has", "been", "than", "more", "over", "days", "day", "months", "month",
        "this", "next", "within", "lakh", "lakhs", "crore", "rs", "rupees", "above", "below", "give", "find", "where",
        "who", "number", "count", "any", "do", "does", "we", "our", "my", "get", "region", "regional", "office",
        "please", "maturing", "expiring", "due", "bank", "banks", "institute", "college", "total"}


@dataclass
class Parsed:
    filters: dict = field(default_factory=dict)
    chips: list[dict] = field(default_factory=list)
    intent: str = "list"
    sort: str = "maturity"
    order: str = "asc"

    def add(self, param: str, value, label: str, label_hi: str) -> None:
        if param in self.filters:
            return
        self.filters[param] = value
        self.chips.append({"param": param, "value": value, "label": label, "label_hi": label_hi})


def _has(text: str, phrase: str) -> bool:
    if re.search(r"[a-z]", phrase):
        return re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", text) is not None
    return phrase in text


def _first(text: str, phrases) -> str | None:
    return next((p for p in sorted(phrases, key=len, reverse=True) if _has(text, p)), None)


def parse(db: Session, question: str) -> Parsed:
    raw = re.sub(r"\s+", " ", question.translate(DEVANAGARI_DIGITS)).strip()
    low = raw.lower()
    p = Parsed()
    consumed: list[str] = []
    if _first(low, COUNT):
        p.intent = "count"

    # Maturity window: "maturing in 30 days", "expiring next 3 months", "90 दिन में परिपक्व"
    m = (re.search(r"(?:matur\w*|expir\w*|due|renewal)\D{0,20}?(\d{1,3})\s*(days?|weeks?|months?|दिन|महीने|माह)", low)
         or re.search(r"(\d{1,3})\s*(days?|weeks?|months?|दिन|महीने|माह)\s*(?:में|के भीतर)", low))
    if m:
        n, u = int(m.group(1)), m.group(2)
        days = n * (7 if u.startswith("week") else 30 if u.startswith(("month", "महीन", "माह")) else 1)
        p.add("expiring_days", days, f"Maturing within {days} days", f"{days} दिनों में परिपक्व")
        consumed.append(m.group(0))
    elif (h := _first(low, ["expiring", "maturing", "due for renewal", "renewal due", "expiring soon", "परिपक्व होने वाले"])):
        p.add("expiring_days", 90, "Maturing within 90 days", "90 दिनों में परिपक्व")
        consumed.append(h)

    for param, value, en, hi, phrases in FLAGS:
        if (h := _first(low, phrases)):
            if param == "matured_unrenewed" and "expiring_days" in p.filters:
                continue
            p.add(param, value, en, hi)
            consumed.extend(x for x in phrases if _has(low, x))
            if param == "at_risk":
                p.sort, p.order = "risk", "desc"
    for value, en, hi, phrases in VERIFICATION:
        if (h := _first(low, phrases)):
            p.add("verification", value, en, hi)
            consumed.extend(x for x in phrases if _has(low, x))
            break
    if not {"matured_unrenewed", "expiring_days"} & p.filters.keys():
        for value, en, hi, phrases in STATUS:
            if (h := _first(low, phrases)):
                p.add("status", value, en, hi)
                consumed.append(h)
                break
    for value, en, hi, phrases in PURPOSE:
        if (h := _first(low, phrases)):
            p.add("purpose", value, en, hi)
            consumed.append(h)
            break
    # Amounts: "above 10 lakh", "more than 5,00,000"
    m = re.search(r"(above|over|more than|at least|below|under|less than|से अधिक|से कम)\s*(?:rs\.?|₹)?\s*([\d,.]+)\s*"
                  r"(lakh|lakhs|crore|cr|लाख|करोड़)?", low)
    if m and (m.group(3) or len(m.group(2).replace(",", "")) >= 5):
        amount = float(m.group(2).replace(",", "") or 0) * {"lakh": 1e5, "lakhs": 1e5, "लाख": 1e5, "crore": 1e7,
                                                              "cr": 1e7, "करोड़": 1e7}.get(m.group(3) or "", 1)
        if m.group(1) in ("below", "under", "less than", "से कम"):
            p.add("max_amount", amount, f"Up to Rs {amount / 1e5:g} lakh", f"₹{amount / 1e5:g} लाख तक")
        else:
            p.add("min_amount", amount, f"Rs {amount / 1e5:g} lakh or more", f"₹{amount / 1e5:g} लाख या अधिक")
            p.sort, p.order = "amount", "desc"
        consumed.append(m.group(0))

    for b in db.scalars(select(Bank)):
        names = [b.name.lower(), b.short_name.lower(), b.code.lower()] + [a.lower() for a in (b.aliases or [])]
        if (h := _first(low, [n for n in names if len(n) >= 3])):
            p.add("bank_id", b.id, b.name, b.name)
            consumed.append(h)
            break
    for r in db.scalars(select(Region)):
        if (h := _first(low, [r.code.lower(), f"{r.city.lower()} region", r.name.lower()])):
            p.add("region_id", r.id, f"{r.name} region", f"{r.code} क्षेत्र")
            consumed.append(h)
            break
    states = {s.code: s for s in db.scalars(select(State))}
    for code, s in states.items():
        if _has(low, s.name.lower()):
            p.add("state_code", code, s.name, s.name)
            consumed.append(s.name.lower())
            break
    else:
        for name, code in STATE_HI.items():
            if name in raw and code in states:
                p.add("state_code", code, states[code].name, name)
                consumed.append(name)
                break
    # An FDR or reference number typed directly.
    if (m := re.search(r"\b(ndh-\d{4}-\d{3,6}|\d{8,16}|[a-z]{2}\d{6,12})\b", low)):
        p.add("q", m.group(1).upper(), f"Number “{m.group(1).upper()}”", f"संख्या “{m.group(1).upper()}”")
        consumed.append(m.group(0))
    # Institution: whatever is left, if it names one institution confidently.
    rest = low
    for c in sorted(consumed, key=len, reverse=True):
        rest = rest.replace(c, " ")
    rest = re.sub(r"[^\w\s.&'-]", " ", rest)
    words = [w for w in rest.split() if w not in STOP and not w.isdigit() and re.search(r"[a-z]", w)]
    if words and any(len(w) >= 4 for w in words):
        guess = " ".join(words)
        best = get_index(db).match(guess, state_code=p.filters.get("state_code")).best
        if best and (best.score >= 0.8 or (best.name_score >= 0.7 and best.score >= 0.6)):
            label = f"{best.name}, {best.city}"
            p.add("institution_id", best.institution_id, label, label)
        elif len(guess) >= 4 and "q" not in p.filters:
            p.add("q", guess, f"Mentions “{guess}”", f"“{guess}” का उल्लेख")
    return p
