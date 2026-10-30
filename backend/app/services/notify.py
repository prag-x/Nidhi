"""Messages to institutions. Written to the outbox; an e-mail or SMS gateway sends them in production."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..enums import NotificationChannel
from ..models import Instrument, Notification


def notify_institution(db: Session, inst: Instrument, subject: str, body: str, *, key: str | None = None,
                       sms: bool = False, at=None) -> Notification | None:
    if key and db.scalar(select(Notification.id).where(Notification.dedup_key == key)):
        return None
    email = inst.institution.email or f"principal@{inst.institution.aicte_pid.replace('-', '')}.example"
    n = Notification(channel=NotificationChannel.EMAIL, recipient=email, institution_id=inst.institution_id,
                     instrument_id=inst.id, subject=subject, body=body, status="SENT", dedup_key=key,
                     created_at=at or utcnow())
    db.add(n)
    if sms and inst.institution.phone:
        db.add(Notification(channel=NotificationChannel.SMS, recipient=inst.institution.phone,
                            institution_id=inst.institution_id, instrument_id=inst.id, subject=subject,
                            body=body[:160], status="SENT", dedup_key=f"{key}:sms" if key else None,
                            created_at=at or utcnow()))
    return n
