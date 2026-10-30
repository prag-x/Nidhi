"""Resolve a free-text institution reference to the institution master.

Signals, combined into one explainable confidence score:
  * AICTE Permanent ID (exact, or one character off as a likely typo)
  * known aliases learned from earlier confirmations
  * character n-gram TF-IDF similarity (robust to typos and abbreviations)
  * token-set and Jaro-Winkler similarity on normalised names
  * similarity of the distinctive part of the name ("Kadamb" in "Kadamb Institute of Technology")
  * acronyms ("KIT Nashik")
  * location agreement: state, city/district, pincode
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
from rapidfuzz import fuzz, process
from rapidfuzz.distance import JaroWinkler, Levenshtein
from sklearn.feature_extraction.text import TfidfVectorizer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..enums import MatchStatus
from ..models import Institution, InstitutionAlias, State
from .normalize import NormalizedName, normalize_name, normalize_pid, normalize_place

AUTO_THRESHOLD = 0.90
REVIEW_THRESHOLD = 0.65
AMBIGUITY_MARGIN = 0.05


@dataclass
class _Record:
    id: int
    pid: str
    name: str
    norm: NormalizedName
    city: str
    district: str
    state_code: str
    state_name: str
    pincode: str | None
    alias_norms: list[str] = field(default_factory=list)

    @property
    def place_tokens(self) -> set[str]:
        return set(normalize_place(f"{self.city} {self.district} {self.state_name}").split())


@dataclass
class Candidate:
    institution_id: int
    name: str
    aicte_pid: str
    city: str
    state_code: str
    score: float
    name_score: float
    reasons: list[str]
    raw_score: float = 0.0  # unclamped, used for ranking and ambiguity

    def as_dict(self) -> dict:
        return {
            "institution_id": self.institution_id,
            "name": self.name,
            "aicte_pid": self.aicte_pid,
            "city": self.city,
            "state_code": self.state_code,
            "score": round(self.score, 4),
            "name_score": round(self.name_score, 4),
            "reasons": self.reasons,
        }


@dataclass
class MatchResult:
    decision: MatchStatus
    confidence: float
    best: Candidate | None
    candidates: list[Candidate]
    normalized_query: str

    def detail(self) -> dict:
        return {
            "decision": self.decision.value,
            "confidence": round(self.confidence, 4),
            "normalized_query": self.normalized_query,
            "candidates": [c.as_dict() for c in self.candidates],
        }


class InstitutionIndex:
    def __init__(self, records: list[_Record]):
        self.records = {r.id: r for r in records}
        self.by_pid = {r.pid: r.id for r in records}
        self.pids = list(self.by_pid)
        self.by_norm: dict[str, set[int]] = defaultdict(set)
        self.by_acronym: dict[str, set[int]] = defaultdict(set)
        texts: list[str] = []
        self.owners: list[int] = []
        for r in records:
            for text in [r.norm.text, *r.alias_norms]:
                if not text:
                    continue
                self.by_norm[text].add(r.id)
                texts.append(text)
                self.owners.append(r.id)
            for acr in r.norm.acronyms:
                if len(acr) >= 2:
                    self.by_acronym[acr].add(r.id)
        self.owners_arr = np.array(self.owners)
        self.vectorizer: TfidfVectorizer | None = None
        self.matrix = None
        if texts:
            self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True)
            self.matrix = self.vectorizer.fit_transform(texts)

    # ------------------------------------------------------------ public API

    def match(
        self,
        raw_name: str,
        pid: str | None = None,
        state_code: str | None = None,
        city: str | None = None,
        pincode: str | None = None,
        limit: int = 5,
        auto_threshold: float = AUTO_THRESHOLD,
        review_threshold: float = REVIEW_THRESHOLD,
    ) -> MatchResult:
        query = normalize_name(raw_name or "")
        pid_n = normalize_pid(pid)
        state_code = (state_code or "").upper() or None
        pincode = (pincode or "").strip() or None
        city_n = normalize_place(city) or None

        pool: dict[int, set[str]] = defaultdict(set)
        exact_pid_id = self.by_pid.get(pid_n) if pid_n else None
        if exact_pid_id:
            pool[exact_pid_id].add("pid")
        near_pid_ids: set[int] = set()
        if pid_n and not exact_pid_id and self.pids:
            for found, _dist, _ in process.extract(
                pid_n, self.pids, scorer=Levenshtein.distance, score_cutoff=1, limit=5
            ):
                near_pid_ids.add(self.by_pid[found])
                pool[self.by_pid[found]].add("pid_near")
        alias_ids = self.by_norm.get(query.text, set())
        for iid in alias_ids:
            pool[iid].add("alias")
        raw_tokens = set(normalize_place(raw_name).split()) | set(query.tokens)
        for tok in raw_tokens:
            for iid in self.by_acronym.get(tok, ()):
                pool[iid].add("acronym")

        tfidf_scores: dict[int, float] = {}
        if self.vectorizer is not None and query.text:
            sims = (self.matrix @ self.vectorizer.transform([query.text]).T).toarray().ravel()
            top = np.argsort(-sims)[:25]
            for idx in top:
                iid = int(self.owners_arr[idx])
                tfidf_scores[iid] = max(tfidf_scores.get(iid, 0.0), float(sims[idx]))
                if sims[idx] > 0.2:
                    pool[iid].add("tfidf")

        candidates = [
            self._score(
                self.records[iid], query, sources, tfidf_scores.get(iid), raw_tokens,
                state_code, city_n, pincode, pid_n, iid == exact_pid_id, iid in near_pid_ids,
            )
            for iid, sources in pool.items()
        ]
        candidates.sort(key=lambda c: c.raw_score, reverse=True)
        candidates = candidates[:limit]
        if not candidates:
            return MatchResult(MatchStatus.UNMATCHED, 0.0, None, [], query.text)

        best = candidates[0]
        margin = best.raw_score - (candidates[1].raw_score if len(candidates) > 1 else 0.0)
        pid_confirmed = best.institution_id == exact_pid_id and best.name_score >= 0.5
        ambiguous = margin < AMBIGUITY_MARGIN and len(candidates) > 1 and not pid_confirmed
        if ambiguous:
            # Two institutions fit equally well; confidence cannot be higher than the tie allows.
            # Cap every near-tied candidate the same way, so the list never shows a lower figure above a higher one.
            for c in candidates:
                if best.raw_score - c.raw_score < AMBIGUITY_MARGIN:
                    c.score = min(c.score, auto_threshold - 0.01)
            best.reasons.append(
                f"Close alternative: {candidates[1].name}, {candidates[1].city} — confirm the right one"
            )
        if best.score >= auto_threshold and not ambiguous:
            decision = MatchStatus.AUTO
        elif best.score >= review_threshold:
            decision = MatchStatus.SUGGESTED
        else:
            decision = MatchStatus.UNMATCHED
        return MatchResult(decision, best.score, best, candidates, query.text)

    # ------------------------------------------------------------ scoring

    def _score(
        self, rec: _Record, query: NormalizedName, sources: set[str], tfidf: float | None,
        raw_tokens: set[str], state_code: str | None, city_n: str | None, pincode: str | None,
        pid_n: str | None, pid_exact: bool, pid_near: bool,
    ) -> Candidate:
        reasons: list[str] = []
        # Drop place names from the query unless they are part of the institution's own name,
        # so "Kadamb Institute of Technology Nashik" compares cleanly with the master name.
        place = rec.place_tokens - set(rec.norm.tokens)
        q_tokens = [t for t in query.tokens if t not in place]
        q_text = " ".join(q_tokens)
        q_distinctive = [t for t in query.distinctive if t not in place]

        best_name = 0.0
        for target in [rec.norm.text, *rec.alias_norms]:
            token_set = fuzz.token_set_ratio(q_text, target) / 100
            jw = JaroWinkler.normalized_similarity(q_text, target)
            tf = tfidf if tfidf is not None else fuzz.ratio(q_text, target) / 100
            target_distinctive = [t for t in target.split() if t in rec.norm.distinctive] or rec.norm.distinctive
            if q_distinctive and target_distinctive:
                dist = fuzz.token_set_ratio(" ".join(q_distinctive), " ".join(target_distinctive)) / 100
                score = 0.30 * tf + 0.25 * token_set + 0.15 * jw + 0.30 * dist
                if dist < 0.5:
                    # Shared generic words ("college of engineering") must not carry a match on their own.
                    score = min(score, 0.35 + 0.5 * dist)
            else:
                score = 0.45 * tf + 0.35 * token_set + 0.20 * jw
            best_name = max(best_name, score)
        name_score = best_name

        if "alias" in sources:
            name_score = 1.0
            reasons.append("Exact match with a known name/alias of this institution")
        else:
            reasons.append(f"Name similarity {round(name_score * 100)}%")
        if query.expansions:
            shown = ", ".join(f"'{a}'→'{b}'" for a, b in query.expansions[:3])
            reasons.append(f"Abbreviations expanded: {shown}")
        acronym_hit = raw_tokens & rec.norm.acronyms
        if acronym_hit and len(next(iter(acronym_hit))) >= 3:
            name_score = max(name_score, 0.80)
            reasons.append(f"Acronym '{next(iter(acronym_hit)).upper()}' matches the institution name")

        score = name_score
        if state_code:
            if state_code == rec.state_code:
                score += 0.04
                reasons.append(f"Same state ({rec.state_name})")
            else:
                score -= 0.20
                reasons.append(f"Different state (given {state_code}, institution in {rec.state_code})")
        city_tokens = set(normalize_place(rec.city).split())
        district_tokens = set(normalize_place(rec.district).split())
        if city_n:
            city_set = set(city_n.split())
            if city_set & (city_tokens | district_tokens) or fuzz.ratio(city_n, normalize_place(rec.city)) >= 88:
                score += 0.06
                reasons.append(f"Same city/district ({rec.city})")
            else:
                score -= 0.08
                reasons.append(f"Different city (given '{city_n}', institution in {rec.city})")
        elif city_tokens and city_tokens <= raw_tokens:
            score += 0.06
            reasons.append(f"City '{rec.city}' mentioned in the name")
        if pincode and rec.pincode:
            if pincode == rec.pincode:
                score += 0.08
                reasons.append(f"Same pincode ({rec.pincode})")
            elif pincode[:3] == rec.pincode[:3]:
                score += 0.03
                reasons.append(f"Same postal area ({pincode[:3]}xxx)")
            else:
                score -= 0.05
                reasons.append("Different pincode")

        if pid_exact:
            if name_score >= 0.5:
                score = max(score, 0.99)
                reasons.insert(0, f"AICTE Permanent ID {rec.pid} matches exactly")
            else:
                score = max(score, 0.80)
                reasons.insert(0, f"AICTE Permanent ID {rec.pid} matches but the name differs — verify")
        elif pid_near and name_score >= 0.7:
            score += 0.08
            reasons.insert(0, f"Permanent ID '{pid_n}' is one character off {rec.pid} (likely typo)")
        elif pid_n and not pid_near:
            reasons.append(f"Permanent ID given ({pid_n}) does not belong to this institution")
            score -= 0.10

        return Candidate(
            institution_id=rec.id,
            name=rec.name,
            aicte_pid=rec.pid,
            city=rec.city,
            state_code=rec.state_code,
            score=float(min(max(score, 0.0), 1.0)),
            name_score=float(min(name_score, 1.0)),
            reasons=reasons,
            raw_score=float(score),
        )


# ---------------------------------------------------------------- cached index

_lock = threading.Lock()
_index: InstitutionIndex | None = None
_signature: tuple | None = None
_checked_at = 0.0
_CHECK_EVERY_SECONDS = 10.0


def _load_records(db: Session) -> list[_Record]:
    state_names = dict(db.execute(select(State.code, State.name)).all())
    aliases: dict[int, list[str]] = defaultdict(list)
    for iid, norm in db.execute(select(InstitutionAlias.institution_id, InstitutionAlias.normalized)):
        aliases[iid].append(norm)
    rows = db.execute(
        select(
            Institution.id, Institution.aicte_pid, Institution.name, Institution.city,
            Institution.district, Institution.state_code, Institution.pincode,
        )
    ).all()
    return [
        _Record(
            id=r.id, pid=r.aicte_pid, name=r.name, norm=normalize_name(r.name), city=r.city,
            district=r.district or r.city, state_code=r.state_code,
            state_name=state_names.get(r.state_code, r.state_code), pincode=r.pincode,
            alias_norms=aliases.get(r.id, []),
        )
        for r in rows
    ]


def _db_signature(db: Session) -> tuple:
    inst = db.execute(select(func.count(Institution.id), func.max(Institution.id))).one()
    alias = db.execute(select(func.count(InstitutionAlias.id), func.max(InstitutionAlias.id))).one()
    return (*inst, *alias)


def get_index(db: Session) -> InstitutionIndex:
    global _index, _signature, _checked_at
    with _lock:
        now = time.monotonic()
        if _index is not None and now - _checked_at < _CHECK_EVERY_SECONDS:
            return _index
        sig = _db_signature(db)
        if _index is None or sig != _signature:
            _index = InstitutionIndex(_load_records(db))
            _signature = sig
        _checked_at = now
        return _index


def invalidate_index() -> None:
    global _index, _signature, _checked_at
    with _lock:
        _index, _signature, _checked_at = None, None, 0.0
