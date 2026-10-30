from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, exists, func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db, utcnow
from ..deps import get_current_user
from ..enums import AlertKind, AlertStatus
from ..models import Alert, AlertRead, User
from ..services.alerts import visible_to
from .serializers import alert_out

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _is_read(user: User):
    return exists().where(and_(AlertRead.alert_id == Alert.id, AlertRead.user_id == user.id))


@router.get("")
def list_alerts(
    status: str = "open",
    kind: AlertKind | None = None,
    unread: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(Alert, _is_read(user).label("read")).where(visible_to(user))
    if status == "open":
        q = q.where(Alert.status != AlertStatus.RESOLVED)
    elif status != "all":
        q = q.where(Alert.status == status.upper())
    if kind:
        q = q.where(Alert.kind == kind)
    if unread:
        q = q.where(~_is_read(user))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.execute(
        q.options(selectinload(Alert.instrument), selectinload(Alert.target_unit))
        .order_by(Alert.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    by_kind = dict(db.execute(
        select(Alert.kind, func.count(Alert.id)).where(visible_to(user), Alert.status != AlertStatus.RESOLVED)
        .group_by(Alert.kind)
    ).all())
    return {"total": total, "page": page, "open_by_kind": by_kind, "items": [{**alert_out(a), "read": bool(r)} for a, r in rows]}


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.scalar(
        select(func.count(Alert.id)).where(visible_to(user), Alert.status != AlertStatus.RESOLVED, ~_is_read(user))
    )
    return {"unread": n}


def _mark_read(db: Session, user: User, alert_ids: list[int]) -> None:
    already = set(db.scalars(select(AlertRead.alert_id).where(AlertRead.user_id == user.id,
                                                              AlertRead.alert_id.in_(alert_ids))))
    for aid in alert_ids:
        if aid not in already:
            db.add(AlertRead(alert_id=aid, user_id=user.id))


@router.post("/{alert_id}/read")
def mark_read(alert_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if db.scalar(select(Alert.id).where(Alert.id == alert_id, visible_to(user))) is None:
        raise HTTPException(404, "Alert not found")
    _mark_read(db, user, [alert_id])
    db.commit()
    return {"ok": True}


@router.post("/read-all")
def read_all(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ids = list(db.scalars(select(Alert.id).where(visible_to(user), Alert.status != AlertStatus.RESOLVED, ~_is_read(user))))
    _mark_read(db, user, ids)
    db.commit()
    return {"marked": len(ids)}


@router.post("/{alert_id}/acknowledge")
def acknowledge(alert_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    alert = db.scalar(select(Alert).where(Alert.id == alert_id, visible_to(user)))
    if alert is None:
        raise HTTPException(404, "Alert not found")
    if alert.status == AlertStatus.OPEN:
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = utcnow()
        alert.acknowledged_by_id = user.id
    _mark_read(db, user, [alert.id])
    db.commit()
    return {"ok": True, "status": alert.status}
