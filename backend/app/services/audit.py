from fastapi import Request
from sqlalchemy.orm import Session

from ..models import AuditLog, User


def client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def audit(
    db: Session,
    user: User | None,
    action: str,
    entity_type: str | None = None,
    entity_id: str | int | None = None,
    request: Request | None = None,
    **details,
) -> None:
    """Record who did what in the hash-chained system ledger. The caller commits with the change."""
    from .ledger import append

    append(
        db,
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            ip=client_ip(request),
            details=details or None,
        )
    )
