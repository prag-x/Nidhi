"""The numbers the portal shows about itself are measured, and stay measured."""

from app.services.evaluation import evaluate_and_store


def test_checks_are_measured_on_planted_faults(db, seeded):
    r = evaluate_and_store(db, n_checks=200, n_docs=60, seed=7, n_scans=6)
    db.rollback()
    c = r["checks"]
    assert c["cases"] == 200
    assert c["precision"] >= 0.95 and c["recall"] >= 0.95, c
    assert c["clean_flagged"] == 0
    assert r["reader"]["field_accuracy"] >= 0.95
    from app.services.fdrdoc import ocr_available

    if ocr_available():
        assert r["scanned"]["field_accuracy"] >= 0.9


def test_proof_page_reports_measured_values(api):
    p = api.get("rb.officer1", "/intelligence/proof").json()
    assert p["evaluation"]["checks"]["precision"] is not None
    assert p["model"]["trained"] is True and p["model"]["auc"] is not None
    assert p["data"]["synthetic"] is True
    assert p["external_services"] == []


def test_dashboard_numbers_add_up(api):
    s = api.get("rb.head", "/dashboard/summary").json()
    k = s["kpis"]
    held = sum(r["count"] for r in s["by_status"] if r["status"] in ("ACTIVE", "EXPIRING", "MATURED",
                                                                     "RELEASE_REQUESTED"))
    assert k["held"] == held
    assert round(sum(b["amount"] for b in s["by_bank"])) == round(k["held_amount"])
    assert sum(r["held"] for r in s["by_region"]) == k["held"]
    listed = api.get("rb.head", "/instruments?status=HELD").json()["total"]
    assert listed == k["held"]


def test_reports_export_in_every_format(api):
    for key in ("status", "maturity", "pending", "discrepancies", "banks", "regions", "releases", "performance"):
        j = api.get("rb.head", f"/reports/{key}").json()
        assert j["columns"]
        for fmt in ("xlsx", "pdf", "csv"):
            r = api.get("rb.head", f"/reports/{key}?format={fmt}")
            assert r.status_code == 200 and len(r.content) > 100, (key, fmt)


def test_ask_reads_questions_in_english_and_hindi(api):
    r = api.post("rb.head", "/ask", {"question": "FDRs maturing in 30 days"}).json()
    assert [c["param"] for c in r["understood"]] == ["expiring_days"]
    r = api.post("rb.head", "/ask", {"question": "90 दिन में परिपक्व होने वाली एफडीआर"}).json()
    assert r["understood"][0]["value"] == 90
    r = api.post("rb.head", "/ask", {"question": "How many FDRs above 10 lakh with Vindhya Bank?"}).json()
    assert {c["param"] for c in r["understood"]} == {"min_amount", "bank_id"} and r["intent"] == "count"
