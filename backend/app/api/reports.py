from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import User
from ..services.audit import audit
from ..services.reports import REPORTS, Filters, institution_history_report, to_csv, to_pdf, to_xlsx

router = APIRouter(prefix="/reports", tags=["reports"])

MEDIA = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
    "csv": "text/csv",
}


def _render(report, fmt: str, user: User, filename: str):
    if fmt == "json":
        return report.as_dict()
    if fmt not in MEDIA:
        raise HTTPException(422, "format must be json, xlsx, pdf or csv")
    body = {"xlsx": lambda: to_xlsx(report, user.full_name), "pdf": lambda: to_pdf(report, user.full_name),
            "csv": lambda: to_csv(report)}[fmt]()
    return Response(body, media_type=MEDIA[fmt], headers={"Content-Disposition": f'attachment; filename="{filename}.{fmt}"'})


@router.get("/institution/{institution_id}")
def institution_history(institution_id: int, request: Request, format: str = "json", db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    from ..models import Institution

    if db.get(Institution, institution_id) is None:
        raise HTTPException(404, "Institution not found")
    if user.role == "INSTITUTION" and user.institution_id != institution_id:
        raise HTTPException(404, "Institution not found")
    report = institution_history_report(db, institution_id)
    if format != "json":
        audit(db, user, "report_exported", "report", "institution", request, institution_id=institution_id, format=format)
        db.commit()
    return _render(report, format, user, f"institution-{institution_id}-history")


@router.get("/{key}")
def run_report(
    key: str,
    request: Request,
    format: str = "json",
    date_from: date | None = None,
    date_to: date | None = None,
    region_id: int | None = None,
    bank_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    builder = REPORTS.get(key)
    if builder is None:
        raise HTTPException(404, f"Unknown report '{key}'")
    if user.role == "INSTITUTION":
        raise HTTPException(403, "Reports are for AICTE staff")
    if user.role == "REGIONAL_OFFICER" and user.org_unit and user.org_unit.region_id:
        region_id = user.org_unit.region_id
    f = Filters.build(date_from, date_to, region_id=region_id, bank_id=bank_id)
    report = builder(db, f)
    if format != "json":
        audit(db, user, "report_exported", "report", key, request, format=format,
              filters={"from": str(f.date_from), "to": str(f.date_to), "region_id": region_id, "bank_id": bank_id})
        db.commit()
    return _render(report, format, user, f"{key}-report-{f.date_to.isoformat()}")
