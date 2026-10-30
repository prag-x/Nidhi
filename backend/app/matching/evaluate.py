"""Measure institution-matching accuracy on synthetic noisy references.

Draws institutions from the database, writes each name the way complainants do (abbreviations,
typos, acronyms, dropped words, case changes, with or without city/state, Permanent ID present,
absent or mistyped) and checks the matcher's decision against the known answer.
"""

import random
from collections import Counter, defaultdict
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..enums import MatchStatus
from ..models import AppSetting, Institution
from .institutions import get_index

RESULT_KEY = "matcher_evaluation"


def evaluate(db: Session, n: int = 3000, seed: int = 7) -> dict:
    from ..seed.generate import noisy_name

    rnd = random.Random(seed)
    insts = db.query(Institution).all()
    if not insts:
        return {"evaluated": 0}
    index = get_index(db)
    outcome: Counter = Counter()
    by_kind: dict[str, Counter] = defaultdict(Counter)
    for _ in range(n):
        inst = rnd.choice(insts)
        raw, kind = noisy_name(rnd, inst)
        pid = None
        if rnd.random() < 0.45:
            pid = inst.aicte_pid
            if rnd.random() < 0.08:
                chars = list(pid)
                k = rnd.randrange(3, len(chars))
                chars[k] = str((int(chars[k]) + 1) % 10)
                pid = "".join(chars)
        result = index.match(
            raw, pid=pid,
            state_code=inst.state_code if rnd.random() < 0.8 else None,
            city=inst.city if rnd.random() < 0.55 else None,
            pincode=inst.pincode if rnd.random() < 0.2 else None,
        )
        correct = result.best is not None and result.best.institution_id == inst.id
        label = {
            MatchStatus.AUTO: "auto_correct" if correct else "auto_wrong",
            MatchStatus.SUGGESTED: "suggested_correct" if correct else "suggested_wrong",
        }.get(result.decision, "unmatched")
        outcome[label] += 1
        by_kind[kind if not pid else f"{kind} + PID"][label] += 1

    auto = outcome["auto_correct"] + outcome["auto_wrong"]
    sugg = outcome["suggested_correct"] + outcome["suggested_wrong"]
    return {
        "evaluated": n,
        "institutions": len(insts),
        "auto": auto,
        "auto_rate": round(auto / n, 4),
        "auto_precision": round(outcome["auto_correct"] / max(auto, 1), 4),
        "auto_wrong": outcome["auto_wrong"],
        "suggested": sugg,
        "suggested_top_correct": round(outcome["suggested_correct"] / max(sugg, 1), 4),
        "unmatched": outcome["unmatched"],
        "top1": round((outcome["auto_correct"] + outcome["suggested_correct"]) / n, 4),
        "by_kind": {k: dict(v) for k, v in sorted(by_kind.items())},
        "run_at": datetime.now(UTC).isoformat(),
    }


def evaluate_and_store(db: Session, n: int = 3000) -> dict:
    result = evaluate(db, n)
    row = db.get(AppSetting, RESULT_KEY)
    if row:
        row.value = result
    else:
        db.add(AppSetting(key=RESULT_KEY, value=result))
    db.flush()
    return result


def stored(db: Session) -> dict | None:
    row = db.get(AppSetting, RESULT_KEY)
    return row.value if row else None
