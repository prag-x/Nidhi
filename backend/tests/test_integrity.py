"""Every change is sealed in a hash chain; editing the database behind the portal's back is detected."""

from sqlalchemy import text

from app.db import SessionLocal
from app.services.ledger import verify_chain, verify_ledger


def test_ledger_and_instrument_chains_verify_after_seeding(api, db):
    v = verify_ledger(db)
    assert v["valid"], v.get("first_break")
    r = api.get("auditor", "/intelligence/proof/verify").json()
    assert r["valid"] is True


def test_tamper_demo_is_detected_and_restored(api):
    r = api.post("admin", "/intelligence/ledger/tamper-demo", {"target": "instrument_event"})
    assert r.status_code == 200, r.text
    try:
        v = api.get("auditor", "/intelligence/ledger/verify").json()
        assert v["valid"] is False
        assert api.get("auditor", "/intelligence/proof/verify").json()["valid"] is False
    finally:
        assert api.post("admin", "/intelligence/ledger/tamper-demo/restore").status_code == 200
    assert api.get("auditor", "/intelligence/ledger/verify").json()["valid"] is True


def test_direct_edit_of_an_amount_breaks_the_instruments_chain(api):
    x = api.lodge()
    with SessionLocal() as s:
        ev_id = s.execute(text("SELECT id, remarks FROM instrument_events WHERE instrument_id = :i ORDER BY seq LIMIT 1"),
                          {"i": x["id"]}).first()
        s.execute(text("UPDATE instrument_events SET remarks = 'edited' WHERE id = :id"), {"id": ev_id[0]})
        s.commit()
        from app.models import Instrument

        assert verify_chain(s.get(Instrument, x["id"]))["valid"] is False
        s.execute(text("UPDATE instrument_events SET remarks = :r WHERE id = :id"), {"r": ev_id[1], "id": ev_id[0]})
        s.commit()
        s.expire_all()
        assert verify_chain(s.get(Instrument, x["id"]))["valid"] is True


def test_every_action_is_in_the_audit_trail(api):
    x = api.lodge()
    api.act("rb.head", x["id"], "observation", remarks="Called the branch to confirm the lien.")
    actions = [r["action"] for r in api.get("auditor", "/admin/audit?page_size=50").json()["items"]]
    assert "instrument_submitted" in actions and "instrument_observation" in actions


def test_documents_and_letters_are_encrypted_at_rest(api):
    from pathlib import Path

    from app.config import get_settings
    from app.models import Document, Letter

    b = api.body()
    x = api.lodge(body=b)
    doc = api.db.get(Document, x["documents"][0]["id"])
    on_disk = (Path(get_settings().upload_dir) / doc.stored_name).read_bytes()
    assert on_disk.startswith(b"NDV1") and b"%PDF" not in on_disk[:64]
    got = api.client.get(f"/api/documents/{doc.id}", headers=api.h("rb.head")).content
    assert got.startswith(b"%PDF")
    import hashlib

    assert hashlib.sha256(got).hexdigest() == doc.sha256
    letter = api.db.query(Letter).filter(Letter.instrument_id == x["id"]).first()
    raw = (Path(get_settings().upload_dir) / "letters" / letter.stored_name).read_bytes()
    assert raw.startswith(b"NDV1")
    # A file altered on disk is refused, not served.
    p = Path(get_settings().upload_dir) / doc.stored_name
    p.write_bytes(on_disk[:-1] + bytes([on_disk[-1] ^ 1]))
    r = api.client.get(f"/api/documents/{doc.id}", headers=api.h("rb.head"))
    assert r.status_code == 409
    p.write_bytes(on_disk)
