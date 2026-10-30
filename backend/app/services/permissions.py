"""Access rules.

Seeing: AICTE officials see every instrument. Regional Office officers see the institutions in their region.
An institution user sees only its own institution's instruments.

Acting, with separation of duties (maker-checker):
- the institution submits instruments, rectifies discrepancies and asks for release;
- the dealing officer (RB) scrutinises, verifies with the bank and recommends release;
- the RB head assigns work, waives discrepancies with a recorded reason and recommends release;
- the competent authority approves release, and never the same person who recommended it;
- Finance & Accounts executes an approved release (lien discharge / refund).
The administrator and the auditor never act on instruments.

Privacy (DPDP Act 2023, data minimisation): institution contact details are masked for the administrator and the
auditor.
"""

from ..enums import HELD_STATUSES, PENDING_SCRUTINY, Role, Status
from ..models import Instrument, User

GLOBAL_ROLES = {Role.ADMIN, Role.COMPETENT_AUTHORITY, Role.RB_HEAD, Role.RB_OFFICER, Role.ACCOUNTS, Role.AUDITOR}
NON_OPERATIONAL = {Role.ADMIN, Role.AUDITOR}
SCRUTINY_ROLES = {Role.RB_OFFICER, Role.RB_HEAD}


def is_global(user: User) -> bool:
    """Sees every instrument across the country."""
    return user.role in GLOBAL_ROLES


def is_management(user: User) -> bool:
    return user.role == Role.COMPETENT_AUTHORITY


def is_institution(user: User) -> bool:
    return user.role == Role.INSTITUTION


def can_view_instrument(user: User, inst: Instrument) -> bool:
    if is_global(user):
        return True
    if user.role == Role.INSTITUTION:
        return user.institution_id == inst.institution_id
    if user.role == Role.REGIONAL_OFFICER:
        return user.org_unit is not None and inst.institution.region_id == user.org_unit.region_id
    return False


def can_submit_for(user: User, institution_id: int) -> bool:
    """Institutions submit their own instruments; RB officers can record one received on paper."""
    if user.role == Role.INSTITUTION:
        return user.institution_id == institution_id
    return user.role in SCRUTINY_ROLES


def can_scrutinise(user: User, inst: Instrument) -> bool:
    """Verify with the bank, record observations, raise or resolve discrepancies, accept or reject."""
    if user.role == Role.RB_HEAD:
        return True
    return user.role == Role.RB_OFFICER and inst.assigned_officer_id in (None, user.id)


def can_assign(user: User) -> bool:
    return user.role == Role.RB_HEAD


def can_waive(user: User) -> bool:
    return user.role == Role.RB_HEAD


def can_rectify(user: User, inst: Instrument) -> bool:
    return user.role == Role.INSTITUTION and user.institution_id == inst.institution_id and \
        inst.status in PENDING_SCRUTINY


def can_request_release(user: User, inst: Instrument) -> bool:
    if inst.status not in HELD_STATUSES or inst.status == Status.RELEASE_REQUESTED:
        return False
    if user.role == Role.INSTITUTION:
        return user.institution_id == inst.institution_id
    return user.role in SCRUTINY_ROLES


def can_recommend_release(user: User) -> bool:
    return user.role in SCRUTINY_ROLES


def can_approve_release(user: User, recommended_by_id: int | None) -> bool:
    """Four eyes: the approver is the competent authority and is never the person who recommended."""
    return user.role == Role.COMPETENT_AUTHORITY and user.id != recommended_by_id


def can_execute_release(user: User) -> bool:
    return user.role == Role.ACCOUNTS


def can_view_pii(user: User) -> bool:
    return user.role not in NON_OPERATIONAL


def mask(value: str | None, keep: int = 2) -> str | None:
    if not value:
        return value
    if "@" in value:
        local, _, domain = value.partition("@")
        return f"{local[:keep]}***@{domain}"
    return "*" * max(len(value) - keep, 0) + value[-keep:]
