"""Tunable rules that administrators can change at runtime without a deployment."""

from sqlalchemy.orm import Session

from ..models import AppSetting, User

DEFAULTS: dict[str, dict] = {
    "reminder_offsets": {"value": "90,60,30,7", "label": "Remind before maturity at these many days (comma-separated)"},
    "expiring_window_days": {"value": 90, "label": "An instrument counts as expiring within (days of maturity)"},
    "renewal_grace_days": {"value": 15, "label": "Escalate to the RB head when a matured instrument is unrenewed after (days)"},
    "renewal_escalate_ca_days": {"value": 45, "label": "Escalate to the competent authority after (days unrenewed)"},
    "verification_sla_days": {"value": 7, "label": "Alert when bank verification is pending longer than (days)"},
    "rectification_days": {"value": 15, "label": "Time given to institutions to rectify discrepancies (days)"},
    "name_match_threshold": {"value": 0.72, "label": "Depositor-name similarity below which a name mismatch is raised"},
    "lien_holder_text": {"value": "Member Secretary, AICTE", "label": "Lien must be marked in favour of"},
    "renewal_risk_alert": {"value": 0.7, "label": "Predicted late-renewal risk at which the officer is alerted"},
    "gateway_enabled": {"value": True, "label": "Use the bank verification gateway where the bank supports it"},
    "reconfirm_days": {"value": 180, "label": "Re-confirm held FDRs with the bank's online service every (days)"},
}


def get_setting(db: Session, key: str):
    row = db.get(AppSetting, key)
    if row is not None:
        return row.value
    return DEFAULTS[key]["value"]


def all_settings(db: Session) -> list[dict]:
    stored = {s.key: s for s in db.query(AppSetting).all()}
    out = []
    for key, meta in DEFAULTS.items():
        row = stored.get(key)
        out.append(
            {
                "key": key,
                "label": meta["label"],
                "value": row.value if row else meta["value"],
                "default": meta["value"],
                "updated_at": row.updated_at if row else None,
            }
        )
    return out


def set_setting(db: Session, key: str, value, user: User) -> None:
    if key not in DEFAULTS:
        raise KeyError(key)
    default = DEFAULTS[key]["value"]
    if isinstance(default, bool):
        value = bool(value)
    elif isinstance(default, int):
        value = int(value)
    elif isinstance(default, float):
        value = float(value)
    else:
        value = str(value).strip()
        if key == "reminder_offsets":
            days = [int(x) for x in value.replace(" ", "").split(",") if x]
            if not days or any(d < 1 or d > 365 for d in days):
                raise ValueError("Reminder offsets must be whole days between 1 and 365")
            value = ",".join(str(d) for d in sorted(set(days), reverse=True))
        elif len(value) < 3:
            raise ValueError("Too short")
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value, updated_by_id=user.id))
    else:
        row.value = value
        row.updated_by_id = user.id
