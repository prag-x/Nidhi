"""Ask the portal: a plain question in English or Hindi, answered from deposit records on this server."""

from urllib.parse import urlencode

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Instrument, User
from ..services import ask as asker
from .instruments import LOAD, SORTS, Filters, filtered
from .serializers import instrument_item

router = APIRouter(prefix="/ask", tags=["ask"])
HOW = "Read on this server with the portal's own vocabularies; no outside AI service."
EXAMPLES = [
    "FDRs maturing in 30 days",
    "Matured and not renewed in Maharashtra",
    "Kadamb Institute of Technology Nashik",
    "Deposits with discrepancies",
    "Awaiting bank reply",
    "Likely to renew late",
    "How many FDRs above 10 lakh with Vindhya Bank?",
    "90 दिन में परिपक्व होने वाली एफडीआर",
    "उत्तर प्रदेश में विसंगतियाँ",
]


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=300)


@router.get("/examples")
def examples(_: User = Depends(get_current_user)):
    return EXAMPLES


@router.post("")
def ask(body: AskIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    parsed = asker.parse(db, body.question)
    if not parsed.chips:
        return {"question": body.question, "understood": [], "intent": parsed.intent, "total": None, "items": [],
                "amount": None, "link": None, "examples": EXAMPLES, "how": HOW}
    f = Filters(**parsed.filters, sort=parsed.sort, order=parsed.order)
    base = filtered(f, user)
    sub = base.with_only_columns(Instrument.id, Instrument.amount).subquery()
    total, amount = db.execute(select(func.count(), func.coalesce(func.sum(sub.c.amount), 0))).one()
    col = SORTS.get(parsed.sort, Instrument.maturity_date)
    ordering = col.asc() if parsed.order == "asc" else col.desc()
    items = db.scalars(base.options(*LOAD).order_by(ordering.nulls_last(), Instrument.id.desc()).limit(8)).all()
    return {
        "question": body.question, "understood": parsed.chips, "intent": parsed.intent, "total": total,
        "amount": float(amount), "items": [instrument_item(x) for x in items],
        "link": "/instruments?" + urlencode({**parsed.filters, "sort": parsed.sort, "order": parsed.order}),
        "how": HOW,
    }
