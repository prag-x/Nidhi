"""Late-renewal prediction.

A gradient-boosted tree model (scikit-learn HistGradientBoostingClassifier) learns from past instruments whose
outcome is known: "looking at this FDR 60 days before it matured, did the replacement arrive after maturity?".
Instruments AICTE now holds are scored with that probability, and every score carries its drivers: how much the
risk would drop if that factor were typical (a local what-if explanation), so an officer sees why, not just a number.

Runs fully offline on the server. Accuracy is measured on past instruments the model did not train on.
"""

from __future__ import annotations

import pickle
import random
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..db import local_date, today, utcnow
from ..enums import HELD_STATUSES, Status
from ..models import AppSetting, Instrument

FEATURES = ["inst_late_rate", "inst_prior", "inst_prior_late", "inst_margin", "inst_worst", "amount_lakh", "tenure_years", "private",
            "gateway_bank", "auto_renewal", "discrepancies", "verify_days", "approval_issue", "new_institution",
            "remote_region"]
EXPLAIN = ["inst_late_rate", "inst_prior_late", "inst_margin", "private", "gateway_bank", "auto_renewal", "discrepancies",
           "verify_days", "approval_issue", "amount_lakh"]
METRICS_KEY = "renewal_model_metrics"
REMOTE_REGIONS = {"NERO", "TVRO"}
LEAD_DAYS = 60


def _driver_text(k: str, f: dict) -> str:
    return {
        "inst_late_rate": f"Institution renewed late {round(f['inst_late_rate'] * 100)}% of the time before",
        "inst_prior_late": f"{int(f['inst_prior_late'])} earlier late renewal(s) by this institution",
        "inst_margin": (f"Earlier renewals arrived {abs(round(f['inst_margin']))} days "
                        f"{'after' if f['inst_margin'] > 0 else 'before'} maturity on average"),
        "private": "Self-financing institution",
        "gateway_bank": "Bank confirms only by letter, so renewals take longer to clear",
        "auto_renewal": "No auto-renewal instruction with the bank",
        "discrepancies": f"{int(f['discrepancies'])} discrepancy(ies) when this FDR was lodged",
        "verify_days": f"Took {int(f['verify_days'])} days to verify last time",
        "approval_issue": "Approval of the institution is under review",
        "amount_lakh": f"Large deposit ({f['amount_lakh']:.0f} lakh)",
    }[k]


MARGINS: dict[int, int] = {}   # instrument id -> days between its maturity and the replacement being lodged


def _margins(insts: list[Instrument]) -> None:
    by_id = {x.id: x for x in insts}
    MARGINS.clear()
    for x in insts:
        old = by_id.get(x.replaces_id) if x.replaces_id else None
        if old is not None and old.renewed_late is not None:
            MARGINS[old.id] = (local_date(x.submitted_at) - old.maturity_date).days


def _features(inst: Instrument, history: list[Instrument]) -> dict:
    """Features as known `LEAD_DAYS` before maturity. `history` = this institution's earlier, settled instruments."""
    settled = [h for h in history if h.renewed_late is not None]
    late = sum(1 for h in settled if h.renewed_late)
    margins = [MARGINS[h.id] for h in settled if h.id in MARGINS]
    verify_days = ((local_date(inst.verified_at) - local_date(inst.submitted_at)).days
                   if inst.verified_at and inst.submitted_at else 10)
    i = inst.institution
    return {
        "inst_late_rate": (late + 0.3) / (len(settled) + 1.5),
        "inst_prior": len(settled),
        "inst_prior_late": late,
        "inst_margin": float(np.mean(margins)) if margins else -30.0,
        "inst_worst": float(max(margins)) if margins else -30.0,
        "amount_lakh": inst.amount / 1e5,
        "tenure_years": (inst.maturity_date - inst.issue_date).days / 365.25,
        "private": float("Private" in (i.ownership or "")),
        "gateway_bank": float(bool(inst.bank and inst.bank.verify_channel == "GATEWAY")),
        "auto_renewal": float(bool(inst.auto_renewal)),
        "discrepancies": float(len(inst.discrepancies)),
        "verify_days": float(max(0, verify_days)),
        "approval_issue": float(i.approval_status != "APPROVED"),
        "new_institution": float(inst.purpose == "NEW_INSTITUTION"),
        "remote_region": float(bool(i.region and i.region.code in REMOTE_REGIONS)),
    }


def _vec(f: dict) -> list[float]:
    return [float(f[k]) for k in FEATURES]


def _model_path() -> Path:
    p = Path(get_settings().model_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p / "renewal_model.pkl"


_model: HistGradientBoostingClassifier | None = None
_baseline: dict | None = None


def _all(db: Session) -> list[Instrument]:
    return db.scalars(select(Instrument).options(
        selectinload(Instrument.institution), selectinload(Instrument.bank),
        selectinload(Instrument.discrepancies))).all()


def _histories(insts: list[Instrument]) -> dict[int, list[Instrument]]:
    by_inst: dict[int, list[Instrument]] = defaultdict(list)
    for x in insts:
        by_inst[x.institution_id].append(x)
    return by_inst


def _prior(history: list[Instrument], inst: Instrument) -> list[Instrument]:
    cutoff = inst.maturity_date - timedelta(days=LEAD_DAYS)
    return [h for h in history if h.id != inst.id and h.maturity_date < cutoff]


def train(db: Session, seed: int = 11) -> dict:
    global _model, _baseline
    insts = _all(db)
    _margins(insts)
    hist = _histories(insts)
    labelled = [x for x in insts if x.renewed_late is not None]
    if len(labelled) < 80:
        return {"trained": False, "reason": "Not enough settled instruments to learn from yet."}
    rows = [(_features(x, _prior(hist[x.institution_id], x)), int(x.renewed_late)) for x in labelled]
    # Hold out by institution so the test measures performance on institutions the model never saw.
    inst_ids = sorted({x.institution_id for x in labelled})
    random.Random(seed).shuffle(inst_ids)
    test_ids = set(inst_ids[: max(1, len(inst_ids) // 5)])
    train_rows = [r for r, x in zip(rows, labelled) if x.institution_id not in test_ids]
    test_rows = [r for r, x in zip(rows, labelled) if x.institution_id in test_ids]
    X = np.array([_vec(f) for f, _ in train_rows])
    y = np.array([lab for _, lab in train_rows])
    Xt = np.array([_vec(f) for f, _ in test_rows])
    yt = np.array([lab for _, lab in test_rows])
    model = HistGradientBoostingClassifier(max_iter=220, learning_rate=0.06, max_leaf_nodes=15, l2_regularization=1.0,
                                           random_state=seed)
    model.fit(X, y)
    p = model.predict_proba(Xt)[:, 1]
    order = np.argsort(-p)
    top = order[: max(1, len(order) // 10)]
    metrics = {
        "trained": True,
        "trained_at": utcnow().isoformat(),
        "train_instruments": int(len(y)),
        "holdout_instruments": int(len(yt)),
        "holdout_institutions": len(test_ids),
        "auc": round(float(roc_auc_score(yt, p)), 3) if len(set(yt)) > 1 else None,
        "average_precision": round(float(average_precision_score(yt, p)), 3) if len(set(yt)) > 1 else None,
        "base_rate": round(float(yt.mean()), 3) if len(yt) else None,
        "precision_top_decile": round(float(yt[top].mean()), 3) if len(top) else None,
        "method": "Gradient-boosted trees (scikit-learn), point-in-time features 60 days before maturity",
    }
    # Refit on everything for scoring.
    full_X = np.vstack([X, Xt]) if len(Xt) else X
    full_y = np.concatenate([y, yt]) if len(yt) else y
    model.fit(full_X, full_y)
    _model = model
    _baseline = {k: float(np.median(full_X[:, FEATURES.index(k)])) for k in FEATURES}
    with _model_path().open("wb") as fh:
        pickle.dump({"model": model, "baseline": _baseline}, fh)
    row = db.get(AppSetting, METRICS_KEY)
    if row is None:
        db.add(AppSetting(key=METRICS_KEY, value=metrics))
    else:
        row.value = metrics
    return metrics


def metrics(db: Session) -> dict:
    row = db.get(AppSetting, METRICS_KEY)
    return row.value if row else {"trained": False}


def _ensure() -> bool:
    global _model, _baseline
    if _model is not None:
        return True
    path = _model_path()
    if path.exists():
        with path.open("rb") as fh:
            data = pickle.load(fh)  # noqa: S301 - our own file, written by train()
        _model, _baseline = data["model"], data["baseline"]
        return True
    return False


def reset() -> None:
    global _model, _baseline
    _model = _baseline = None


def score_held(db: Session) -> int:
    """Score every instrument AICTE holds that has no replacement yet."""
    if not _ensure():
        return 0
    insts = _all(db)
    _margins(insts)
    hist = _histories(insts)
    targets = [x for x in insts if x.status in HELD_STATUSES and x.status != Status.RELEASE_REQUESTED]
    succ_of = {x.replaces_id for x in insts if x.replaces_id and x.status != Status.REJECTED}
    targets = [x for x in targets if x.id not in succ_of]
    if not targets:
        return 0
    feats = [_features(x, _prior(hist[x.institution_id], x)) for x in targets]
    X = np.array([_vec(f) for f in feats])
    base = _model.predict_proba(X)[:, 1]
    drivers: list[list[dict]] = [[] for _ in targets]
    for k in EXPLAIN:
        j = FEATURES.index(k)
        X2 = X.copy()
        X2[:, j] = _baseline[k]
        delta = base - _model.predict_proba(X2)[:, 1]
        for i, d in enumerate(delta):
            if d > 0.03:
                drivers[i].append({"factor": k, "impact": round(float(d), 3), "text": _driver_text(k, feats[i])})
    for i, x in enumerate(targets):
        x.renewal_risk = round(float(base[i]), 3)
        x.renewal_drivers = sorted(drivers[i], key=lambda d: -d["impact"])[:4]
    return len(targets)


def ensure_model(db: Session) -> dict:
    m = metrics(db)
    if not m.get("trained") or not _ensure():
        m = train(db)
    return m


def days_to(inst: Instrument) -> int:
    return (inst.maturity_date - today()).days
