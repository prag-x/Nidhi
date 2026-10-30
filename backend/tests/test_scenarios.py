"""The six test scenarios named in PS 26265, end to end through the API."""

from datetime import timedelta

from dateutil.relativedelta import relativedelta
import pytest
from sqlalchemy import select

from app.db import SessionLocal, today
from app.models import Alert, Instrument, Notification
from app.services.instruments import WorkflowError
from app.services.monitor import run_monitor
from tests.conftest import SAMPLES


def codes(x: dict, status="OPEN") -> set[str]:
    return {d["code"] for d in x["discrepancies"] if d["status"] == status}


# ---------------------------------------------------------------- 1. new FDR submission


def test_new_fdr_submission_reads_document_verifies_with_bank_and_is_accepted(api):
    # The institution uploads its FDR copy; the portal reads it to pre-fill the form.
    pdf = (SAMPLES / "kadamb_renewal_fdr.pdf").read_bytes()
    r = api.client.post("/api/instruments/read-document", headers=api.h("kadamb"),
                        files={"file": ("fdr.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    read = r.json()
    assert read["values"]["fdr_number"] == "40045520917"
    assert read["values"]["amount"] == 1_500_000
    inst = api.institution()
    body = api.body(inst, fdr="40045520917", amount=1_500_000, purpose="NEW_PROGRAMME", ifsc="BHRT0004521",
                    branch="Nashik Station Road", issue_date=read["values"]["issue_date"],
                    maturity_date=read["values"]["maturity_date"], document_token=read["token"])
    body.pop("institution_id")
    x = api.lodge("kadamb", body)
    assert x["ref_no"].startswith("NDH-")
    assert x["status"] == "SUBMITTED"
    assert x["documents"] and x["documents"][0]["doc_type"] == "FDR_COPY"
    # An acknowledgement letter with a public verification code was issued.
    letters = api.get("kadamb", f"/instruments/{x['id']}/letters").json()
    assert [l["kind"] for l in letters] == ["ACKNOWLEDGEMENT"]
    assert api.client.get(f"/api/public/verify/{letters[0]['code']}").json()["valid"] is True
    # Declared, document and bank values are kept apart; the officer verifies online and accepts.
    x = api.act("rb.head", x["id"], "verify")
    assert x["verification_status"] == "CONFIRMED"
    rows = {r["field"]: r for r in x["compare"]}
    assert rows["amount"]["declared"] == rows["amount"]["document"] == rows["amount"]["bank"] == 1_500_000
    assert all(r["bank_agrees"] for r in x["compare"])
    x = api.act("rb.head", x["id"], "accept", remarks="All particulars confirmed by the bank.")
    assert x["status"] in ("ACTIVE", "EXPIRING")
    assert {e["event_type"] for e in x["events"]} >= {"SUBMITTED", "BANK_VERIFIED", "ACCEPTED"}


def test_institution_cannot_lodge_for_another_institution(api):
    other = api.institution("Udaan Institute of Management", "Lucknow")
    x = api.lodge("kadamb", api.body(other))
    assert x["institution"]["id"] == api.user("kadamb").institution_id


def test_bank_without_online_service_gets_a_letter_and_officer_records_reply(api):
    b = api.body(bank="SNDB")
    assert api.bank("SNDB").verify_channel == "LETTER"
    x = api.lodge(body=b)
    x = api.act("rb.head", x["id"], "verify")
    assert x["verification_status"] == "REQUESTED"
    kinds = [l["kind"] for l in api.get("rb.head", f"/instruments/{x['id']}/letters").json()]
    assert "BANK_VERIFICATION" in kinds
    vals = {k: b[k] for k in ("fdr_number", "amount", "issue_date", "maturity_date", "depositor_name", "lien_holder")}
    x = api.act("rb.head", x["id"], "bank_reply", found=True, bank_values=vals, reference="BR/2026/118")
    assert x["verification_status"] == "CONFIRMED"


# ---------------------------------------------------------------- 2. validity tracking and 3. approaching maturity


def test_monitor_tracks_validity_and_sends_reminders_once(api):
    b = api.body(months=36)
    api.bank_knows(b)
    x = api.lodge(body=b)
    api.act("rb.head", x["id"], "verify")
    x = api.act("rb.head", x["id"], "accept")
    assert x["status"] == "ACTIVE"
    maturity = today().fromisoformat(b["maturity_date"])
    with SessionLocal() as s:
        run_monitor(s, on=maturity - timedelta(days=29))
        s.commit()
        inst = s.get(Instrument, x["id"])
        assert inst.status == "EXPIRING"
        assert set(inst.reminders_sent) >= {90, 60, 30}
        n_alerts = s.scalar(select(Alert.id).where(Alert.instrument_id == inst.id).limit(1))
        assert n_alerts is not None
        sent = s.scalars(select(Notification).where(Notification.instrument_id == inst.id)).all()
        assert any("Renewal due" in n.subject for n in sent)
        before = len(sent)
        run_monitor(s, on=maturity - timedelta(days=28))  # nothing new is due
        s.commit()
        assert len(s.scalars(select(Notification).where(Notification.instrument_id == inst.id)).all()) == before
        # The institution sees its own reminder.
    alerts = api.get("kadamb", "/alerts").json()["items"]
    assert any(a["instrument_id"] == x["id"] for a in alerts)
    with SessionLocal() as s:
        run_monitor(s, on=maturity + timedelta(days=20))
        s.commit()
        inst = s.get(Instrument, x["id"])
        assert inst.status == "MATURED"
        assert inst.escalation_level == 1   # past the 15-day grace: RB head
        run_monitor(s, on=maturity + timedelta(days=50))
        s.commit()
        assert s.get(Instrument, x["id"]).escalation_level == 2   # past 45 days: competent authority


def test_short_validity_is_flagged_against_the_deposit_norm(api):
    x = api.lodge(months=12)
    assert "VALIDITY_SHORT" in codes(x)


# ---------------------------------------------------------------- 4. renewal


def test_renewal_replaces_the_old_fdr_and_keeps_the_history(api):
    old_b = api.body(months=36)
    api.bank_knows(old_b)
    old = api.lodge(body=old_b)
    api.act("rb.head", old["id"], "verify")
    old = api.act("rb.head", old["id"], "accept")
    new_b = api.body(months=36, replaces_id=old["id"])
    api.bank_knows(new_b)
    new = api.lodge("kadamb", new_b)
    assert new["replaces"]["id"] == old["id"]
    api.act("rb.head", new["id"], "verify")
    new = api.act("rb.head", new["id"], "accept")
    old = api.get("rb.head", f"/instruments/{old['id']}").json()
    assert old["status"] == "RENEWED"
    assert old["renewed_late"] is False
    prof = api.get("rb.head", f"/institutions/{old['institution']['id']}").json()
    chain = next(c for c in prof["chains"] if c["instruments"][0]["id"] == old["id"])
    assert [i["id"] for i in chain["instruments"]] == [old["id"], new["id"]]


def test_renewal_must_point_at_a_held_instrument_of_the_same_institution(api):
    mine = api.user("kadamb").institution_id
    held = api.db.scalar(select(Instrument).where(Instrument.institution_id != mine,
                                                  Instrument.status.in_(["ACTIVE", "EXPIRING"])).limit(1))
    api.lodge("kadamb", api.body(replaces_id=held.id), expect=422)


# ---------------------------------------------------------------- 5. discrepancy identification


def test_discrepancies_are_found_and_rectified(api):
    b = api.body(amount=50_000, lien_holder="Self")
    x = api.lodge(body=b)
    found = codes(x)
    assert {"AMOUNT_SHORT", "LIEN_MISSING"} <= found
    x = api.act("rb.head", x["id"], "send_for_rectification")
    assert x["status"] == "DISCREPANCY"
    # Acceptance is impossible while discrepancies are open.
    api.act("rb.head", x["id"], "accept", expect=409)
    fixed = {"amount": 500_000, "lien_holder": "Member Secretary, AICTE"}
    api.bank_knows({**b, **fixed})
    # The institution uploads the fresh FDR copy and corrects the declared particulars.
    r = api.client.post(f"/api/instruments/{x['id']}/documents", headers=api.h("kadamb"),
                        files={"file": ("fresh.pdf", api.pdf({**b, **fixed}), "application/pdf")})
    assert r.status_code == 201, r.text
    x = api.act("kadamb", x["id"], "rectify", corrections=fixed, remarks="Fresh FDR for the full amount.")
    assert x["status"] == "UNDER_SCRUTINY"
    assert not {"AMOUNT_SHORT", "LIEN_MISSING"} & codes(x)
    api.act("rb.head", x["id"], "verify")
    assert api.act("rb.head", x["id"], "accept")["status"] == "ACTIVE"


def test_altered_document_is_caught(api):
    pdf = (SAMPLES / "kadamb_renewal_fdr_altered.pdf").read_bytes()
    read = api.client.post("/api/instruments/read-document", headers=api.h("kadamb"),
                           files={"file": ("fdr.pdf", pdf, "application/pdf")}).json()
    b = api.body(amount=1_500_000, document_token=read["token"])
    x = api.lodge("kadamb", b)
    assert "DOCUMENT_MISMATCH" in codes(x)


def test_reused_fdr_raises_a_fraud_signal(api):
    b = api.body()
    api.bank_knows(b)
    first = api.lodge(body=b)
    api.act("rb.head", first["id"], "verify")
    api.act("rb.head", first["id"], "accept")
    other = api.institution("Udaan Institute of Management", "Lucknow")
    dup = api.lodge(body=api.body(other, fdr=b["fdr_number"]))
    assert "DUPLICATE_INSTRUMENT" in codes(dup)
    assert any(a["kind"] == "FRAUD_SIGNAL" and a["instrument_id"] == dup["id"]
               for a in api.get("rb.head", "/alerts?page_size=100").json()["items"])


def test_bank_reply_that_differs_is_a_discrepancy(api):
    b = api.body(amount=500_000)
    api.bank_knows(b, amount=50_000)
    x = api.lodge(body=b)
    x = api.act("rb.head", x["id"], "verify")
    assert x["verification_status"] == "MISMATCH"
    assert "BANK_MISMATCH" in codes(x)
    row = next(r for r in x["compare"] if r["field"] == "amount")
    assert row["declared"] == 500_000 and row["bank"] == 50_000 and row["bank_agrees"] is False


def test_bank_with_no_record(api):
    x = api.lodge()
    x = api.act("rb.head", x["id"], "verify")
    assert x["verification_status"] == "NOT_FOUND"
    assert "BANK_NOT_FOUND" in codes(x)


def test_waiver_needs_the_rb_head_and_a_reason(api):
    x = api.lodge(months=12)
    d = next(d for d in x["discrepancies"] if d["code"] == "VALIDITY_SHORT")
    officer = api.handle_of(x["assigned_officer"]["id"])
    api.act(officer, x["id"], "waive_discrepancy", expect=403, discrepancy_id=d["id"], remarks="Fine by me, really.")
    api.act("rb.head", x["id"], "waive_discrepancy", expect=422, discrepancy_id=d["id"], remarks="ok")
    x = api.act("rb.head", x["id"], "waive_discrepancy", discrepancy_id=d["id"],
                remarks="Tenure relaxed by the Council's order for this programme.")
    assert "VALIDITY_SHORT" in codes(x, "WAIVED")


# ---------------------------------------------------------------- 6. authorised release


def _held(api) -> dict:
    b = api.body()
    api.bank_knows(b)
    x = api.lodge(body=b)
    api.act("rb.head", x["id"], "verify")
    return api.act("rb.head", x["id"], "accept")


CHECKLIST = {k: {"ok": True, "note": "Checked with the file."}
             for k in ("no_liability", "no_regulatory_matter", "approval_position", "documents_returned")}


def test_release_follows_maker_checker_and_issues_lien_release_letter(api):
    x = _held(api)
    x = api.act("kadamb", x["id"], "release_request", reason="CLOSURE", remarks="Programme closed, no students on roll.")
    assert x["status"] == "RELEASE_REQUESTED"
    # Every condition must be checked before it can be recommended.
    api.act("rb.head", x["id"], "release_recommend", expect=409,
            checklist={**CHECKLIST, "no_liability": {"ok": False, "note": ""}})
    api.act("rb.head", x["id"], "release_recommend", checklist=CHECKLIST, remarks="Conditions met.")
    # Only the competent authority approves; the institution and accounts cannot.
    api.act("kadamb", x["id"], "release_decide", expect=403, approve=True)
    api.act("accounts", x["id"], "release_decide", expect=403, approve=True)
    api.act("accounts", x["id"], "release_execute", expect=409)   # not approved yet
    api.act("ms", x["id"], "release_decide", approve=True, remarks="Approved.")
    x = api.act("accounts", x["id"], "release_execute", remarks="Lien discharged.")
    assert x["status"] == "RELEASED"
    letter = next(l for l in api.get("accounts", f"/instruments/{x['id']}/letters").json() if l["kind"] == "LIEN_RELEASE")
    pub = api.client.get(f"/api/public/verify/{letter['code']}").json()
    assert pub["valid"] and pub["kind"] == "LIEN_RELEASE"
    assert "•" in pub["instrument"]["fdr_last4"]
    # The downloaded PDF matches the issued one byte for byte; an edited copy does not.
    pdf = api.client.get(f"/api/letters/{letter['code']}/pdf", headers=api.h("accounts")).content
    ok = api.client.post(f"/api/public/verify/{letter['code']}/file", files={"file": ("l.pdf", pdf)}).json()
    bad = api.client.post(f"/api/public/verify/{letter['code']}/file", files={"file": ("l.pdf", pdf + b" ")}).json()
    assert ok["matches"] is True and bad["matches"] is False


def test_recommender_cannot_also_approve(api, db):
    from app.services import release

    x = _held(api)
    api.act("kadamb", x["id"], "release_request", reason="PERIOD_COMPLETED")
    inst = db.get(Instrument, x["id"])
    r = inst.releases[-1]
    ms = api.user("ms")
    release.recommend(db, r, ms, CHECKLIST, None)   # even if the same person recommended at the service level...
    with pytest.raises(WorkflowError):
        release.decide(db, r, ms, True, None)        # ...they can never approve their own recommendation
    db.rollback()


def test_replaced_release_needs_an_accepted_successor(api):
    x = _held(api)
    api.act("kadamb", x["id"], "release_request", expect=409, reason="REPLACED")


def test_rejected_release_returns_the_instrument_to_held(api):
    x = _held(api)
    api.act("kadamb", x["id"], "release_request", reason="OTHER", remarks="Please release.")
    api.act("rb.head", x["id"], "release_recommend", checklist=CHECKLIST)
    x = api.act("ms", x["id"], "release_decide", approve=False, remarks="Liability under review.")
    assert x["status"] in ("ACTIVE", "EXPIRING")


# ---------------------------------------------------------------- seeded demo scenarios are present


def test_seeded_demo_scenarios(seeded, api):
    sc = seeded["scenarios"]
    for key in ("Duplicate FDR (fraud signal)", "Matured, unrenewed, escalated", "Bank has no record",
                "Release: awaiting approval"):
        assert key in sc
    matured = api.get("rb.head", "/instruments?matured_unrenewed=true&q=Nachiketa").json()
    assert matured["total"] >= 1
    nach = next(i for i in matured["items"] if i["institution"]["name"].startswith("Nachiketa"))
    assert nach["status"] == "MATURED"


def test_photo_of_an_fdr_is_read_by_ocr(api):
    import io

    import pytest

    from app.services.fdrdoc import ocr_available

    if not ocr_available():
        pytest.skip("Tesseract is not installed")
    import pypdfium2 as pdfium

    b = api.body(amount=750_000, fdr="T0045037177")
    img = pdfium.PdfDocument(api.pdf(b))[0].render(scale=200 / 72).to_pil().convert("L")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    r = api.client.post("/api/instruments/read-document", headers=api.h("kadamb"),
                        files={"file": ("photo.jpg", buf.getvalue(), "image/jpeg")})
    assert r.status_code == 200, r.text
    v = r.json()["values"]
    assert v["amount"] == 750_000
    from app.services.checks import compare_values

    assert compare_values("fdr_number", b["fdr_number"], v["fdr_number"])  # OCR look-alikes (T/7, O/0) are tolerated
    x = api.lodge("kadamb", {**b, "document_token": r.json()["token"]})
    assert x["documents"][0]["filename"].endswith(".jpg")
    assert x["doc_extract"]["amount"] == 750_000
    assert not any(d["code"] == "DOCUMENT_MISMATCH" for d in x["discrepancies"])


def test_dates_are_compared_in_indian_time_not_utc(api, db):
    """An FDR issued today and lodged just after midnight IST (still yesterday in UTC) is not 'issued after lodging'."""
    from datetime import datetime, timezone

    from app.db import local_date
    from app.services import checks

    x = api.lodge()
    inst = db.get(Instrument, x["id"])
    inst.submitted_at = datetime(2026, 10, 30, 19, 10, tzinfo=timezone.utc)   # 00:40 IST on 31 Oct
    inst.issue_date = local_date(inst.submitted_at)
    assert inst.issue_date.isoformat() == "2026-10-31"
    assert "DATES_INCONSISTENT" not in {f.code for f in checks.evaluate(db, inst)}
    db.rollback()
