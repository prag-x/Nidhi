"""Periodic work: the maturity monitor and re-scoring of late-renewal risk."""

from sqlalchemy.orm import Session

from . import prediction
from .monitor import run_monitor


def run_sweep(db: Session) -> dict:
    scored = prediction.score_held(db)
    stats = run_monitor(db)
    stats["scored"] = scored
    db.commit()
    return stats
