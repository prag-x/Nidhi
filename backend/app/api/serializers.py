"""ORM → JSON shapes shared by the API routers."""

from ..db import today
from ..enums import HELD_STATUSES, DiscrepancyStatus
from ..models import Alert, Bank, Discrepancy, Document, Institution, Instrument, InstrumentEvent, Letter, OrgUnit, \
    ReleaseRequest, User, Verification
from ..services.checks import FIELD_LABELS, RULES
from ..services.instruments import EVENT_LABELS
from ..services.permissions import can_view_pii, mask


def unit_ref(u: OrgUnit | None) -> dict | None:
    if u is None:
        return None
    return {"id": u.id, "code": u.code, "name": u.name, "unit_type": u.unit_type}


def user_ref(u: User | None) -> dict | None:
    if u is None:
        return None
    return {"id": u.id, "full_name": u.full_name, "designation": u.designation}


def user_out(u: User) -> dict:
    return {
        "id": u.id, "email": u.email, "full_name": u.full_name, "designation": u.designation, "role": u.role,
        "phone": u.phone, "is_active": u.is_active, "org_unit": unit_ref(u.org_unit),
        "institution": institution_ref(u.institution) if u.institution_id else None,
        "last_login_at": u.last_login_at, "created_at": u.created_at,
    }


def bank_ref(b: Bank | None) -> dict | None:
    if b is None:
        return None
    return {"id": b.id, "code": b.code, "name": b.name, "short_name": b.short_name, "verify_channel": b.verify_channel,
            "sector": b.sector, "is_scheduled": b.is_scheduled}


def institution_ref(i: Institution | None) -> dict | None:
    if i is None:
        return None
    return {"id": i.id, "name": i.name, "aicte_pid": i.aicte_pid, "city": i.city, "state_code": i.state_code,
            "region_id": i.region_id}


def institution_out(i: Institution, viewer: User | None = None, stats: dict | None = None) -> dict:
    pii = viewer is None or can_view_pii(viewer)
    return {
        **institution_ref(i),
        "inst_type": i.inst_type, "ownership": i.ownership, "society_name": i.society_name, "address": i.address,
        "district": i.district, "state_name": i.state.name if i.state else i.state_code, "pincode": i.pincode,
        "region": {"id": i.region.id, "code": i.region.code, "name": i.region.name, "city": i.region.city}
        if i.region else None,
        "established_year": i.established_year, "approved_intake": i.approved_intake,
        "approval_status": i.approval_status,
        "email": i.email if pii else mask(i.email), "phone": i.phone if pii else mask(i.phone),
        "lat": i.lat, "lon": i.lon, "stats": stats,
    }


def days_to_maturity(inst: Instrument) -> int:
    return (inst.maturity_date - today()).days


def instrument_item(x: Instrument) -> dict:
    return {
        "id": x.id, "ref_no": x.ref_no, "kind": x.kind, "purpose": x.purpose, "approval_year": x.approval_year,
        "institution": institution_ref(x.institution), "bank": bank_ref(x.bank), "bank_name_raw": x.bank_name_raw,
        "fdr_number": x.fdr_number, "amount": x.amount, "required_amount": x.required_amount,
        "issue_date": x.issue_date, "maturity_date": x.maturity_date, "days_to_maturity": days_to_maturity(x),
        "status": x.status, "verification_status": x.verification_status,
        "open_discrepancies": x.open_discrepancies, "max_severity": x.max_severity,
        "assigned_officer": user_ref(x.assigned_officer), "submitted_at": x.submitted_at,
        "last_action_at": x.last_action_at, "last_action_summary": x.last_action_summary,
        "next_action": x.next_action, "renewal_risk": x.renewal_risk if x.status in HELD_STATUSES else None,
        "replaces_id": x.replaces_id, "auto_renewal": x.auto_renewal,
    }


def event_out(e: InstrumentEvent) -> dict:
    return {
        "id": e.id, "seq": e.seq, "event_type": e.event_type, "label": EVENT_LABELS.get(e.event_type, e.event_type),
        "occurred_at": e.occurred_at, "actor": user_ref(e.actor_user), "actor_label": e.actor_label,
        "from_status": e.from_status, "to_status": e.to_status, "remarks": e.remarks, "meta": e.meta,
        "hash": e.hash, "prev_hash": e.prev_hash, "documents": [document_out(d) for d in e.documents],
    }


def document_out(d: Document) -> dict:
    return {"id": d.id, "doc_type": d.doc_type, "filename": d.filename, "content_type": d.content_type,
            "size_bytes": d.size_bytes, "sha256": d.sha256, "uploaded_at": d.uploaded_at,
            "uploaded_by": user_ref(d.uploaded_by)}


def discrepancy_out(d: Discrepancy) -> dict:
    title, _sev = RULES.get(d.code, (d.code, d.severity))
    return {
        "id": d.id, "code": d.code, "title": title, "severity": d.severity, "field": d.field,
        "field_label": FIELD_LABELS.get(d.field or "", d.field), "message": d.message, "expected": d.expected,
        "found": d.found, "source": d.source, "status": d.status, "raised_at": d.raised_at,
        "resolved_at": d.resolved_at, "resolved_by": user_ref(d.resolved_by), "resolution_note": d.resolution_note,
        "related": {"id": d.related_instrument.id, "ref_no": d.related_instrument.ref_no,
                    "institution": institution_ref(d.related_instrument.institution)}
        if d.related_instrument else None,
    }


def verification_out(v: Verification) -> dict:
    return {"id": v.id, "channel": v.channel, "status": v.status, "bank_values": v.bank_values,
            "differences": v.differences, "reference": v.reference, "requested_at": v.requested_at,
            "responded_at": v.responded_at, "requested_by": user_ref(v.requested_by)}


def release_out(r: ReleaseRequest) -> dict:
    from ..services.release import REASON_LABELS

    return {
        "id": r.id, "reason": r.reason, "reason_label": REASON_LABELS.get(r.reason, r.reason), "details": r.details,
        "status": r.status, "checklist": r.checklist or {}, "requested_by": user_ref(r.requested_by),
        "requested_at": r.requested_at, "recommended_by": user_ref(r.recommended_by),
        "recommended_at": r.recommended_at, "approved_by": user_ref(r.approved_by), "approved_at": r.approved_at,
        "executed_by": user_ref(r.executed_by), "executed_at": r.executed_at, "decision_note": r.decision_note,
        "letter_code": r.letter_code,
    }


def letter_out(letter: Letter) -> dict:
    return {"id": letter.id, "code": letter.code, "kind": letter.kind, "addressee": letter.addressee,
            "subject": letter.subject, "sha256": letter.sha256, "issued_at": letter.issued_at,
            "issued_by": user_ref(letter.issued_by), "revoked": letter.revoked}


def compare_rows(x: Instrument) -> list[dict]:
    """Declared, read from the document, and confirmed by the bank, field by field."""
    from ..services.checks import compare_values

    latest = next((v for v in reversed(x.verifications) if v.status not in ("REQUESTED",)), None)
    bank = (latest.bank_values or {}) if latest and latest.status != "NOT_FOUND" else {}
    doc = x.doc_extract or {}
    rows = []
    for f in ("fdr_number", "amount", "issue_date", "maturity_date", "depositor_name", "lien_holder"):
        declared = getattr(x, f)
        if hasattr(declared, "isoformat"):
            declared = declared.isoformat()
        d_val, b_val = doc.get(f), bank.get(f) if bank else None
        rows.append({
            "field": f, "label": FIELD_LABELS[f], "declared": declared, "document": d_val, "bank": b_val,
            "document_agrees": None if d_val is None else compare_values(f, declared, d_val),
            "bank_agrees": None if not bank else (compare_values(f, declared, b_val) if f != "lien_holder"
                                                  else bool(b_val) and "aicte" in str(b_val).lower()),
        })
    return rows


def instrument_out(x: Instrument, viewer: User) -> dict:
    from ..services import permissions as P

    open_d = [d for d in x.discrepancies if d.status == DiscrepancyStatus.OPEN]
    return {
        **instrument_item(x),
        "institution": institution_out(x.institution, viewer),
        "branch": x.branch, "ifsc": x.ifsc, "depositor_name": x.depositor_name, "lien_holder": x.lien_holder,
        "application_ref": x.application_ref, "required_valid_until": x.required_valid_until,
        "doc_extract": x.doc_extract, "doc_extract_confidence": x.doc_extract_confidence,
        "verified_at": x.verified_at, "accepted_at": x.accepted_at, "closed_at": x.closed_at,
        "submitted_by": user_ref(x.submitted_by), "escalation_level": x.escalation_level,
        "renewal_drivers": x.renewal_drivers or [], "renewed_late": x.renewed_late,
        "compare": compare_rows(x),
        "discrepancies": [discrepancy_out(d) for d in x.discrepancies],
        "open_discrepancy_list": [discrepancy_out(d) for d in open_d],
        "verifications": [verification_out(v) for v in x.verifications],
        "documents": [document_out(d) for d in x.documents],
        "releases": [release_out(r) for r in x.releases],
        "events": [event_out(e) for e in x.events],
        "replaces": {"id": x.replaces.id, "ref_no": x.replaces.ref_no, "status": x.replaces.status,
                     "maturity_date": x.replaces.maturity_date} if x.replaces else None,
        "permissions": {
            "scrutinise": P.can_scrutinise(viewer, x) and x.status in ("SUBMITTED", "UNDER_SCRUTINY", "DISCREPANCY"),
            "assign": P.can_assign(viewer),
            "waive": P.can_waive(viewer),
            "rectify": P.can_rectify(viewer, x),
            "request_release": P.can_request_release(viewer, x),
            "recommend_release": P.can_recommend_release(viewer),
            "approve_release": viewer.role == "COMPETENT_AUTHORITY",
            "execute_release": P.can_execute_release(viewer),
            "renew": (viewer.role == "INSTITUTION" and viewer.institution_id == x.institution_id
                      or viewer.role in ("RB_OFFICER", "RB_HEAD")) and x.status in HELD_STATUSES
                     and x.status != "RELEASE_REQUESTED",
            "reverify": viewer.role in ("RB_OFFICER", "RB_HEAD") and x.status in HELD_STATUSES,
        },
    }


def alert_out(a: Alert) -> dict:
    return {
        "id": a.id, "kind": a.kind, "severity": a.severity, "title": a.title, "message": a.message,
        "instrument_id": a.instrument_id, "institution_id": a.institution_id,
        "ref_no": a.instrument.ref_no if a.instrument else None, "status": a.status, "created_at": a.created_at,
        "target_unit": unit_ref(a.target_unit), "target_role": a.target_role,
    }
