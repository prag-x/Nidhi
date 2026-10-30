"""One small seeded portal per test session; each test lodges its own fresh instruments where it changes state."""

import os
import tempfile
from datetime import timedelta
from itertools import count
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="nidhi-test-"))
os.environ.update({
    # Set NIDHI_TEST_DATABASE_URL to run the suite against PostgreSQL.
    "NIDHI_DATABASE_URL": os.environ.get("NIDHI_TEST_DATABASE_URL", f"sqlite:///{_tmp / 'test.db'}"),
    "NIDHI_ENVIRONMENT": "test",
    "NIDHI_SCHEDULER_ENABLED": "false",
    "NIDHI_BCRYPT_ROUNDS": "4",
    "NIDHI_SECRET_KEY": "test-secret-key-that-is-long-enough-for-hs256",
    "NIDHI_UPLOAD_DIR": str(_tmp / "uploads"),
    "NIDHI_MODEL_DIR": str(_tmp / "models"),
    "NIDHI_DEMO_MODE": "true",
})

import pytest  # noqa: E402
from dateutil.relativedelta import relativedelta  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import models  # noqa: E402, F401
from app.db import Base, SessionLocal, engine, today  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Bank, BankRecord, Institution, Instrument, User  # noqa: E402
from app.security import login_limiter, public_track_limiter  # noqa: E402
from app.seed.generate import DEMO_PASSWORD, seed  # noqa: E402

SAMPLES = _tmp / "samples"
LIEN = "Member Secretary, AICTE"
_n = count(1)


@pytest.fixture(scope="session")
def seeded():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    s = SessionLocal()
    summary = seed(s, n_institutions=80, samples_dir=SAMPLES, log=lambda *_: None)
    s.commit()
    s.close()
    return summary


@pytest.fixture
def db(seeded):
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def client(seeded):
    login_limiter.reset()
    public_track_limiter.reset()
    with TestClient(app) as c:
        yield c


class Api:
    """Signs in as demo users, calls the API, and lodges fresh instruments."""

    def __init__(self, client: TestClient, db):
        self.client, self.db, self._tokens = client, db, {}

    def token(self, handle: str) -> str:
        if handle not in self._tokens:
            r = self.client.post("/api/auth/login", json={"email": f"{handle}@nidhi.test", "password": DEMO_PASSWORD})
            assert r.status_code == 200, r.text
            self._tokens[handle] = r.json()["access_token"]
        return self._tokens[handle]

    def h(self, handle):
        return {"Authorization": f"Bearer {self.token(handle)}"}

    def get(self, handle, path, **kw):
        return self.client.get(f"/api{path}", headers=self.h(handle), **kw)

    def post(self, handle, path, json=None, **kw):
        return self.client.post(f"/api{path}", json=json, headers=self.h(handle), **kw)

    def user(self, handle) -> User:
        return self.db.scalar(select(User).where(User.email == f"{handle}@nidhi.test"))

    def institution(self, name="Kadamb Institute of Technology", city="Nashik") -> Institution:
        return self.db.scalar(select(Institution).where(Institution.name == name, Institution.city == city))

    def bank(self, code="BHRT") -> Bank:
        return self.db.scalar(select(Bank).where(Bank.code == code))

    def body(self, inst: Institution | None = None, *, bank="BHRT", amount=500_000, months=36, purpose="NEW_PROGRAMME",
             fdr=None, **over) -> dict:
        inst = inst or self.institution()
        issue = today() - timedelta(days=3)
        b = {"institution_id": inst.id, "purpose": purpose, "approval_year": "2026-27",
             "fdr_number": fdr or f"T{next(_n):04d}{os.getpid() % 10000:04d}77", "bank_id": self.bank(bank).id,
             "branch": f"{inst.city} Main", "ifsc": f"{bank}0001234", "depositor_name": inst.society_name,
             "amount": amount, "issue_date": issue.isoformat(),
             "maturity_date": (issue + relativedelta(months=months)).isoformat(), "lien_holder": LIEN}
        b.update(over)
        return b

    def bank_knows(self, b: dict, **over) -> None:
        """Put the FDR in the simulated bank's books, as the bank would have it."""
        rec = BankRecord(bank_id=b["bank_id"], fdr_number=b["fdr_number"], branch=b["branch"], ifsc=b["ifsc"],
                         depositor_name=b["depositor_name"], amount=b["amount"],
                         issue_date=today().fromisoformat(b["issue_date"]),
                         maturity_date=today().fromisoformat(b["maturity_date"]), lien_holder=b.get("lien_holder"),
                         status="LIVE")
        for k, v in over.items():
            setattr(rec, k, v)
        self.db.add(rec)
        self.db.commit()

    def pdf(self, b: dict, **over) -> bytes:
        from app.services.fdrdoc import draw_specimen

        v = {**b, **over}
        return draw_specimen(bank_name=self.db.get(Bank, v["bank_id"]).name, branch=v["branch"], ifsc=v["ifsc"],
                            fdr_number=v["fdr_number"], amount=v["amount"],
                            issue_date=today().fromisoformat(v["issue_date"]),
                            maturity_date=today().fromisoformat(v["maturity_date"]), depositor=v["depositor_name"],
                            lien_holder=v.get("lien_holder"), rate=7.0, style=0)

    def document(self, b: dict, handle="rb.officer1", **over) -> str:
        """A specimen FDR PDF showing these particulars, read by the portal; returns the staged token."""
        pdf = self.pdf(b, **over)
        r = self.client.post("/api/instruments/read-document", headers=self.h(handle),
                             files={"file": ("fdr.pdf", pdf, "application/pdf")})
        assert r.status_code == 200, r.text
        return r.json()["token"]

    def lodge(self, handle="rb.officer1", body=None, expect=201, with_doc=True, **kw) -> dict:
        body = dict(body or self.body(**kw))
        if with_doc and "document_token" not in body:
            body["document_token"] = self.document(body, handle)
        r = self.post(handle, "/instruments", body)
        assert r.status_code == expect, r.text
        return r.json()

    def act(self, handle, inst_id, action, expect=200, **payload) -> dict:
        r = self.post(handle, f"/instruments/{inst_id}/actions/{action}", payload)
        assert r.status_code == expect, r.text
        return r.json()

    def officer_for(self, x: dict) -> str:
        return (x["assigned_officer"] or {}).get("full_name") and self.handle_of(x["assigned_officer"]["id"]) or "rb.head"

    def handle_of(self, user_id: int) -> str:
        return self.db.get(User, user_id).email.split("@")[0]

    def instrument(self, inst_id) -> Instrument:
        self.db.expire_all()
        return self.db.get(Instrument, inst_id)


@pytest.fixture
def api(client, db):
    return Api(client, db)
