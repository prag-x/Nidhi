"""What an evaluator would click: every role's pages, the PS 26265 scenarios in the browser, letters and the ledger."""

import re
from pathlib import Path

import pytest
from conftest import BASE
from playwright.sync_api import expect

ROLES = ["rb.head", "rb.officer1", "ms", "accounts", "ro.wro", "auditor", "admin", "kadamb"]
STAFF_PAGES = ["/", "/instruments", "/maturity", "/releases", "/institutions", "/alerts", "/ask", "/overview",
               "/reports", "/proof", "/verify"]
INST_PAGES = ["/", "/instruments", "/alerts", "/verify"]
SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def test_login_page_shows_the_three_sources_and_demo_accounts(anon):
    p = anon.go("/login")
    body = anon.text()
    for hint in ("Declared", "Bank confirmed", "Dealing officer", "Kadamb Institute of Technology"):
        assert hint.lower() in body.lower(), hint
    p.fill("input[type=email]", "rb.head@nidhi.test")
    p.fill("input[type=password]", "wrong-password")
    p.click("button[type=submit]")
    p.wait_for_timeout(1200)
    assert "/login" in p.url
    assert not anon.errors


@pytest.mark.parametrize("handle", ROLES)
def test_every_page_renders_for_every_role(signin, handle):
    s = signin(handle)
    for path in INST_PAGES if handle == "kadamb" else STAFF_PAGES:
        s.go(path)
        body = s.text()
        assert len(body) > 150, (handle, path)
        assert "Something went wrong" not in body, (handle, path)
    assert not s.errors, s.errors[:5]


def test_institution_sees_only_its_own_deposits(signin):
    s = signin("kadamb")
    s.go("/instruments")
    names = s.page.locator("tbody tr").all_inner_texts()
    assert names and all("Udaan" not in n for n in names)
    assert s.page.get_by_role("link", name="Overview").count() == 0


def test_renewal_with_document_is_read_lodged_and_acknowledged(signin):
    s = signin("kadamb")
    s.go("/")
    s.page.get_by_role("link", name=re.compile(r"NDH-")).first.click()
    s.settle()
    s.page.get_by_role("link", name="Lodge renewal").click()
    s.settle()
    s.page.set_input_files("input[type=file]", str(SAMPLES / "kadamb_renewal_fdr.pdf"))
    expect(s.page.get_by_text(re.compile(r"100% of the fields read"))).to_be_visible(timeout=15000)
    s.page.get_by_role("button", name="Lodge", exact=True).click()
    s.page.wait_for_url(re.compile(r"/instruments/\d+$"), timeout=20000)
    s.settle()
    body = s.text()
    assert "Declared by institution" in body and "Read from FDR copy" in body
    assert "Acknowledgement" in body
    assert not s.errors, s.errors[:5]


def test_officer_verifies_with_bank_and_accepts(signin):
    s = signin("rb.head")
    s.go("/instruments?status=PENDING&verification=UNVERIFIED")
    link = s.page.locator("a[href^='/instruments/']").filter(has_text=re.compile("NDH-")).first
    if link.count() == 0:
        pytest.skip("no unverified deposit pending in this data set")
    link.click()
    s.settle()
    s.page.get_by_role("button", name=re.compile("Verify with bank now|Send verification letter")).click()
    s.settle(1200)
    assert re.search(r"Bank confirmed|Awaiting bank|Bank reply differs|Bank has no record", s.text())
    assert not s.errors, s.errors[:5]


def test_altered_document_is_flagged_in_red(signin):
    s = signin("rb.head")
    s.go("/instruments?q=Medhavi")
    s.page.locator("a[href^='/instruments/']").filter(has_text=re.compile("NDH-")).first.click()
    s.settle()
    assert "Uploaded document differs from what was declared" in s.text()
    expect(s.page.locator("td.bg-seal-50").first).to_be_visible()


def test_competent_authority_sees_release_to_approve(signin):
    s = signin("ms")
    s.go("/")
    assert "Releases awaiting your approval" in s.text()
    s.go("/releases")
    assert "To approve" in s.text()


def test_letter_can_be_verified_publicly(anon):
    req = anon.page.request
    tok = req.post(f"{BASE}/api/auth/login", data={"email": "rb.head@nidhi.test", "password": "Demo@2026"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    released = req.get(f"{BASE}/api/instruments?status=RELEASED", headers=h).json()["items"][0]
    code = req.get(f"{BASE}/api/instruments/{released['id']}/letters", headers=h).json()[-1]["code"]
    p = anon.go(f"/verify/{code}")
    expect(p.get_by_text("Genuine. Issued by the AICTE deposit portal.")).to_be_visible(timeout=10000)
    anon.go("/verify/NDL-00000000")
    expect(anon.page.get_by_text("Not issued by the portal")).to_be_visible(timeout=10000)


def test_ask_in_hindi(signin):
    s = signin("rb.head")
    s.go("/ask")
    s.page.fill("#ask-input", "90 दिन में परिपक्व होने वाली एफडीआर")
    s.page.keyboard.press("Enter")
    expect(s.page.get_by_text("Maturing within 90 days")).to_be_visible(timeout=10000)


def test_tamper_demo_is_detected(signin):
    s = signin("admin")
    s.go("/integrity")
    expect(s.page.get_by_text("Nothing has been altered")).to_be_visible(timeout=30000)
    s.page.get_by_role("button", name="Rewrite a bank-verification record").click()
    s.settle(800)
    s.page.get_by_role("button", name="Verify now").click()
    try:
        expect(s.page.get_by_text("Tampering detected")).to_be_visible(timeout=30000)
    finally:
        s.page.get_by_role("button", name="Undo the edit").click()
        s.settle(800)
    s.page.get_by_role("button", name="Verify now").click()
    expect(s.page.get_by_text("Nothing has been altered")).to_be_visible(timeout=30000)
