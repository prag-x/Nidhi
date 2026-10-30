from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from ..db import utcnow
from ..enums import AlertKind, AlertStatus, Severity
from ..models import Alert, AlertRead, User
from .events import queue_event
from .permissions import is_management


def raise_alert(
    db: Session,
    *,
    kind: AlertKind,
    severity: Severity,
    title: str,
    message: str,
    dedup_key: str,
    instrument_id: int | None = None,
    institution_id: int | None = None,
    target_unit_id: int | None = None,
    target_user_id: int | None = None,
    target_role: str | None = None,
    reopen: bool = False,
) -> Alert | None:
    """Create an alert once per dedup key. Returns the alert if it is new (or was reopened)."""
    existing = db.scalar(select(Alert).where(Alert.dedup_key == dedup_key))
    if existing is not None:
        if not reopen:
            return None
        existing.title, existing.message, existing.severity = title, message, severity
        existing.status = AlertStatus.OPEN
        existing.created_at = utcnow()
        existing.acknowledged_at = existing.resolved_at = existing.acknowledged_by_id = None
        db.execute(delete(AlertRead).where(AlertRead.alert_id == existing.id))
        alert = existing
    else:
        alert = Alert(
            kind=kind, severity=severity, title=title, message=message, dedup_key=dedup_key,
            instrument_id=instrument_id, institution_id=institution_id,
            target_unit_id=target_unit_id, target_user_id=target_user_id, target_role=target_role,
            status=AlertStatus.OPEN,
        )
        db.add(alert)
    db.flush()
    queue_event(
        db,
        "alert",
        {"id": alert.id, "kind": kind, "severity": severity, "title": title, "message": message,
         "instrument_id": instrument_id,
         "institution_id": institution_id if target_role == "INSTITUTION" else None},
        unit_ids={target_unit_id} if target_unit_id else set(),
        user_ids={target_user_id} if target_user_id else set(),
    )
    return alert


def resolve_alerts(db: Session, *, instrument_id: int | None = None, kinds=None) -> int:
    q = select(Alert).where(Alert.status != AlertStatus.RESOLVED)
    if instrument_id is not None:
        q = q.where(Alert.instrument_id == instrument_id)
    if kinds:
        q = q.where(Alert.kind.in_(list(kinds)))
    n = 0
    for alert in db.scalars(q).all():
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = utcnow()
        n += 1
    return n


def visible_to(user: User) -> ColumnElement[bool]:
    """Alerts a user should see in their inbox."""
    if user.institution_id:
        # Institution users see only alerts addressed to their own institution.
        return and_(Alert.institution_id == user.institution_id, Alert.target_role == "INSTITUTION")
    mine = [Alert.target_user_id == user.id, Alert.target_role == user.role]
    if user.org_unit_id:
        mine.append(and_(Alert.target_unit_id == user.org_unit_id, Alert.target_user_id.is_(None)))
    if is_management(user):
        mine.append(Alert.severity == Severity.CRITICAL)
    return or_(*mine)
