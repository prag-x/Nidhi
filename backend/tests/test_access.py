"""Who can see and do what. Institutions see only their own deposits; nobody approves their own recommendation."""

from sqlalchemy import select

from app.models import Instrument


def test_institution_sees_only_its_own_instruments(api):
    mine = api.user("kadamb").institution_id
    items = api.get("kadamb", "/instruments?page_size=200").json()["items"]
    assert items and all(i["institution"]["id"] == mine for i in items)
    other = api.db.scalar(select(Instrument).where(Instrument.institution_id != mine).limit(1))
    assert api.get("kadamb", f"/instruments/{other.id}").status_code == 404
    assert api.get("kadamb", f"/institutions/{other.institution_id}").status_code == 404
    assert api.get("kadamb", "/reports/maturity").status_code == 403
    assert all(i["id"] == mine for i in api.get("kadamb", "/institutions").json()["items"])


def test_institution_alerts_are_only_its_own(api):
    mine = api.user("kadamb").institution_id
    for a in api.get("kadamb", "/alerts?status=all&page_size=100").json()["items"]:
        assert a["institution_id"] == mine


def test_regional_officer_sees_only_the_region(api):
    ro = api.user("ro.wro")
    region = ro.org_unit.region_id
    items = api.get("ro.wro", "/instruments?page_size=200").json()["items"]
    assert items and all(i["institution"]["region_id"] == region for i in items)
    x = api.lodge()
    api.act("ro.wro", x["id"], "accept", expect=403)


def test_staff_role_boundaries(api):
    x = api.lodge()
    for handle in ("auditor", "admin", "accounts", "ms", "kadamb"):
        api.act(handle, x["id"], "verify", expect=403)
        api.act(handle, x["id"], "accept", expect=403)
    for handle in ("rb.officer1", "kadamb", "accounts"):
        assert api.get(handle, "/admin/users").status_code == 403
    assert api.post("auditor", "/admin/sweep").status_code == 403
    assert api.post("rb.head", "/intelligence/ledger/tamper-demo", {}).status_code == 403


def test_officer_works_only_on_own_files(api):
    x = api.lodge()
    owner = api.handle_of(x["assigned_officer"]["id"])
    other = next(h for h in ("rb.officer1", "rb.officer2", "rb.officer3", "rb.officer4") if h != owner)
    api.act(other, x["id"], "start_scrutiny", expect=403)
    api.act(owner, x["id"], "start_scrutiny")
    api.act("rb.head", x["id"], "assign", officer_id=api.user(other).id)
    api.act(other, x["id"], "observation", remarks="Checked the society's registration certificate.")


def test_contact_details_are_masked_for_read_only_roles(api):
    inst = api.institution()
    full = api.get("rb.head", f"/institutions/{inst.id}").json()
    masked = api.get("auditor", f"/institutions/{inst.id}").json()
    if full["email"]:
        assert masked["email"] != full["email"]


def test_live_updates_never_reach_other_institutions():
    from app.services.events import Subscriber, _wants

    inst_a = Subscriber(user_id=1, unit_id=None, is_global=False, institution_id=10)
    staff = Subscriber(user_id=2, unit_id=None, is_global=True)
    assert _wants(inst_a, {"institution_id": 10}, None, None)
    assert not _wants(inst_a, {"institution_id": 11}, None, None)
    assert not _wants(inst_a, {"institution_id": None}, set(), set())
    assert _wants(staff, {"institution_id": 11}, None, None)
