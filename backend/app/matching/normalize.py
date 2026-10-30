"""Text normalisation for Indian institution names.

Complaints spell the same institution many ways: "Shri Kadamb Inst. of Engg. & Tech., Nashik",
"S.K.I.E.T Nashik", "Sri Kadamb Institute of Engineering and Technology". Normalising them to a
canonical token form before fuzzy matching removes most of that noise.
"""

import re
import unicodedata
from dataclasses import dataclass, field

ABBREVIATIONS = {
    "engg": "engineering", "eng": "engineering", "engr": "engineering", "engineeering": "engineering",
    "tech": "technology", "techn": "technology", "technol": "technology", "techno": "technology",
    "inst": "institute", "instt": "institute", "insti": "institute", "institue": "institute",
    "institution": "institute", "institutions": "institute", "instit": "institute",
    "coll": "college", "clg": "college", "colg": "college", "col": "college",
    "univ": "university", "uni": "university",
    "mgmt": "management", "mgt": "management", "mngt": "management", "manag": "management",
    "sci": "science", "sciences": "science",
    "pharm": "pharmacy", "pharma": "pharmacy", "pharmaceutical": "pharmacy",
    "poly": "polytechnic", "polytech": "polytechnic",
    "arch": "architecture",
    "res": "research", "edu": "education", "educ": "education",
    "comp": "computer", "appl": "applications", "info": "information",
    "intl": "international", "natl": "national", "govt": "government", "gov": "government",
    "sri": "shri", "shree": "shri", "sree": "shri", "shrimati": "smt", "srimati": "smt",
    "centre": "center", "studies": "study",
}
HONORIFICS = {"shri", "smt", "dr", "late", "sh", "prof", "kumari", "km"}
STOPWORDS = {"of", "the", "and", "for", "in", "at", "a", "an", "pvt", "ltd", "private", "limited"}
GENERIC_WORDS = {
    "institute", "college", "engineering", "technology", "management", "university", "school",
    "polytechnic", "science", "research", "study", "pharmacy", "academy", "group", "campus",
    "education", "society", "trust", "foundation", "center", "applications", "computer", "hotel",
    "catering", "architecture", "professional", "advanced", "information", "integrated", "memorial",
    "women", "womens", "girls", "technical", "degree", "post", "graduate", "business", "administration",
}

# Former and colloquial names of Indian cities/states seen in complaints.
PLACE_ALIASES = {
    "bombay": "mumbai", "madras": "chennai", "bangalore": "bengaluru", "calcutta": "kolkata", "poona": "pune",
    "gurgaon": "gurugram", "mysore": "mysuru", "mangalore": "mangaluru", "trivandrum": "thiruvananthapuram",
    "cochin": "kochi", "baroda": "vadodara", "allahabad": "prayagraj", "benaras": "varanasi", "banaras": "varanasi",
    "hubli": "hubballi", "belgaum": "belagavi", "gulbarga": "kalaburagi", "calicut": "kozhikode",
    "trichy": "tiruchirappalli", "pondicherry": "puducherry", "pondy": "puducherry", "orissa": "odisha",
    "vizag": "visakhapatnam", "vishakhapatnam": "visakhapatnam", "bezawada": "vijayawada", "nasik": "nashik",
    "aurangabad": "aurangabad", "sambhajinagar": "aurangabad", "uttaranchal": "uttarakhand", "simla": "shimla",
    "jubbulpore": "jabalpur", "cawnpore": "kanpur", "benares": "varanasi", "kalikut": "kozhikode",
}

_SPLIT = re.compile(r"[^\w]+", re.UNICODE)


@dataclass
class NormalizedName:
    raw: str
    text: str                       # canonical form used for fuzzy comparison
    tokens: list[str]
    distinctive: list[str]          # tokens that are not generic words
    acronyms: set[str]
    expansions: list[tuple[str, str]] = field(default_factory=list)


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    decomposed = unicodedata.normalize("NFKD", text)
    if sum(ord(c) < 128 for c in decomposed) >= 0.9 * max(len(decomposed), 1):
        text = "".join(c for c in decomposed if not unicodedata.combining(c))
    return text.lower()


def _merge_initials(tokens: list[str]) -> list[str]:
    """['a', 'b', 'c', 'college'] -> ['abc', 'college'] so dotted initials compare as one token."""
    merged: list[str] = []
    run: list[str] = []
    for tok in tokens:
        if len(tok) == 1 and tok.isalpha():
            run.append(tok)
            continue
        if run:
            merged.append("".join(run))
            run = []
        merged.append(tok)
    if run:
        merged.append("".join(run))
    return merged


def normalize_name(raw: str) -> NormalizedName:
    folded = _fold(raw or "").replace("&", " and ")
    tokens = _merge_initials([t for t in _SPLIT.split(folded) if t])
    expansions: list[tuple[str, str]] = []
    expanded: list[str] = []
    for tok in tokens:
        tok = PLACE_ALIASES.get(tok, tok)
        full = ABBREVIATIONS.get(tok)
        if full:
            if full != tok and len(tok) < len(full):
                expansions.append((tok, full))
            tok = full
        expanded.append(tok)

    with_honorifics = [t for t in expanded if t not in STOPWORDS]
    core = [t for t in with_honorifics if t not in HONORIFICS]
    distinctive = [t for t in core if t not in GENERIC_WORDS and not t.isdigit()]

    acronyms = set()
    for seq in (core, with_honorifics):
        if len(seq) >= 2:
            acronyms.add("".join(t[0] for t in seq))
    return NormalizedName(
        raw=raw,
        text=" ".join(core),
        tokens=core,
        distinctive=distinctive,
        acronyms=acronyms,
        expansions=expansions,
    )


def normalize_pid(pid: str | None) -> str | None:
    """AICTE Permanent IDs look like '1-12345678'. Accept common variants such as '1 12345678'."""
    if not pid:
        return None
    cleaned = re.sub(r"[^0-9-]", "", pid.strip().replace(" ", "-").replace("_", "-"))
    if not cleaned:
        return None
    if "-" not in cleaned and len(cleaned) > 6 and cleaned.startswith("1"):
        cleaned = f"1-{cleaned[1:]}"
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or None


def normalize_place(text: str | None) -> str:
    return " ".join(PLACE_ALIASES.get(t, t) for t in _SPLIT.split(_fold(text or "")) if t)
