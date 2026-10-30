# Nidhi (निधि) — team handoff

*SIH 2026 · PS 26265 · Team SignalNine (198001) · updated 30 Oct 2026*

## Objective

- Ship a **fully working** prototype for **PS 26265**, the AICTE Security Deposit / FDR Management Portal. It is called **Nidhi**, lives in its own repository, and reuses the foundations of Ekmat (our PS 26264 entry).
- Submit it with the **6-slide SIH deck**, the submission text, a short demo video, and a live deployment on Render.

## Key Context & Constraints

- **Team and PS.** Team SignalNine, Team ID 198001. The same team also submitted Ekmat (PS 26264); Ekmat's repo is `github.com/prag-x/Ekmat` and its demo is at `ekmat-signalnine.onrender.com`. The deadline was "at most 2 days" from 30 Oct 2026.
- **No pushing.** Claude must never push to GitHub. Aaryaman uploads through the GitHub web UI from Windows. The local folder used for Ekmat was `C:\Users\aarya\OneDrive\Desktop\samanvay`.
- **Honest numbers only.** Every number in the deck or README must be measured or sourced; no invented impact percentages.
- **Synthetic data.** Banks and institutions are fictional. Generated FDRs carry the watermark *SYNTHETIC SPECIMEN – NOT A BANK DOCUMENT*. Deposit amounts and tenures are demonstration values, not AICTE norms.
- **Deck rules.** At most 6 slides, on the official SIH template.
- **Stack.**
  - Back end: FastAPI, SQLAlchemy 2, Alembic, SQLite or PostgreSQL 16, scikit-learn, RapidFuzz, ReportLab, pypdf, Tesseract OCR (pytesseract and pypdfium2).
  - Front end: React 19, Vite, TypeScript, Tailwind 4, TanStack Query, Recharts.
  - Browser tests: Playwright.
- **Configuration.** Environment variables use the `NIDHI_` prefix. Letters carry QR codes that point to `NIDHI_PUBLIC_BASE_URL`. In `deploy/Dockerfile` that defaults to `https://nidhi-signalnine.onrender.com` through the build argument `PUBLIC_BASE_URL`.
- **Demo accounts.** All use password `Demo@2026`, all `@nidhi.test`:
  - `rb.head`, `rb.officer1`–`rb.officer4`
  - `ms` (competent authority), `accounts`, `auditor`, `admin`, `ro.wro`
  - institutions: `kadamb`, `udaan`
- **Gotcha: the backend venv.** Always call the venv as `.venv/bin/python -m …` (for example `python -m uvicorn`, `python -m pip`). The `.venv/bin/uvicorn` and `.venv/bin/pip` scripts in the dev container point at another environment.
- **Gotcha: killing the server.** Don't `pkill -f "uvicorn app.main"` from a shell whose own command line contains that text, because it kills the shell. Find the PID first.

## Decisions Made

- **Separate repo** reusing Ekmat's foundations → keeps both entries clean. *Rejected:* one monorepo for both PSs.
- **Name Nidhi (निधि, "fund held in trust")**, same team and ID → the user chose it.
- **Declared, document and bank values are kept apart** (`doc_extract` and `Verification.bank_values` are never merged into the declared fields) → the PS explicitly requires the distinction. It is also the signature screen.
- **Bank verification is a pluggable connector**: a simulated online gateway, plus a letter route where the officer records the bank's reply → no real bank API is available. A connector interface plus letters is how the system would actually be deployed.
- **Periodic re-confirmation** of held FDRs every 180 days, by the monitor → catches FDRs closed at the branch after AICTE accepted them.
- **Release is maker-checker.** The steps are request → RB recommends after 4 conditions → competent authority approves → Accounts executes and issues the lien-release letter. The approver can never be the recommender → the PS requires authorisation by the competent authority.
- **Letters are PDFs with a code, a QR and a SHA-256 hash**, checked on a public `/verify` page → banks can check them without an account.
- **"Late" means the institution lodged the replacement after the old FDR matured**, not the date AICTE accepted it → AICTE's own processing time shouldn't count against the institution. This also fixed an AUC of 0.50.
- **Late-renewal model** with history features (average and worst margin of earlier renewals) → AUC 0.65 on held-out institutions. We report it honestly as modest.
- **`verified_at` is the first confirmation only**; re-confirmations go in the verification log → otherwise the turnaround KPI was 444 days.
- **Depositor-name matching penalises a distinctive word that appears on one side only** → "Sri Tapasya Vidya Trust" ≠ "Tapasya Education Society".
- **OCR with Tesseract**, offline → handles scans and photos. FDR numbers are folded for OCR look-alikes (T/7, O/0, S/5 and so on) so OCR misreads don't raise false document mismatches.
- **Stale seeded deposits are rejected and re-lodged** with a scheduled bank → avoids unrealistic files "under scrutiny for 7 years".
- **Docker is used on Render, not locally.** Render builds `deploy/Dockerfile`. There was no Docker daemon in the dev container, so the image build itself is **untested**; the same steps were verified by hand on a fresh copy.
- **Theme on the title slide: "Smart Automation"** → copied from 26264. **Needs confirming.**

## Work Completed

**Back end:** 23 tables, one Alembic migration.

- **Workflow:** lodge, scrutinise, verify, rectify, accept or reject, renew, release.
- **Checks:** 17 automatic rules, plus discrepancies an officer raises. Fraud alerts for a reused FDR or document, a bank with no record, and an FDR closed at the bank.
- **Reader:** reads the FDR copy (PDF text layer, or Tesseract OCR for scans and PNG/JPG photos) and pre-fills the form.
- **Bank connector:** online, or by letter.
- **Letters:** ACK, BANK_VERIFICATION, RECTIFICATION and LIEN_RELEASE, each a PDF with a QR; public verification by code and by uploading the PDF.
- **Monitor:** reminders at 90/60/30/7 days, escalation at 15 and 45 days, re-confirmation, chasing bank replies, renewal-risk alerts, and a notifications outbox.
- **Dashboard and analysis:** dashboard and role queues, 8 reports (Excel/PDF/CSV), an institution history report, Ask in English and Hindi.
- **Integrity:** hash-chained ledger, tamper demo, a Proof page with live measurements.
- **Access:** 8 roles. Live updates are scoped so institutions only receive their own events.

**Front end:** about 18 pages.

- Role desks, the deposit list, the deposit file (three-source comparison, discrepancies, bank, release, history, documents and letters), lodge or renew with upload and pre-fill.
- Maturity calendar (redesigned chart plus heat-map month tiles), releases, institutions and their renewal chains, the Overview (redesigned coloured KPI tiles and charts).
- Reports, alerts, Ask, Proof, integrity, admin (users, deposit norms, reminders, outbox, audit, system), and the public Verify page.
- Visual identity: banknote teal, violet stamp colour for confirmations, Anek Latin and Mukta fonts.

**Measured** on the 600-institution demo dataset (seed 2026):

| What | Result |
|---|---|
| Checks, on 500 planted cases | precision 1.00, recall 1.00, 0 of 50 clean deposits flagged |
| Reader, 300 digital FDRs | 100% of fields |
| OCR, 45 scanned/skewed/blurred FDRs | 99.6% of fields |
| Late-renewal model | AUC 0.65; top 10% flagged → 81% actually late (base rate 44%) |
| Ledger verification | 15,091 entries in about 1 s |
| Backend tests | 64 passing, on SQLite and PostgreSQL 16 |
| Browser tests | 17 passing |
| Fresh-copy install | seed and tests pass |

**Docs and deliverables:**

- README with run instructions for Windows/macOS/Linux, Render, demo accounts, letter verification, requirement mapping, measurements, offline AI, tests, security, project layout and credits.
- `docs/DEMO.md`: a 12-minute walkthrough.
- Screenshots.
- `docs/Nidhi_SIH2026_SignalNine.pptx` and `.pdf`: 6 slides on the SIH template.
- `docs/HANDOFF.md` (this file).
- `render.yaml`, `deploy/Dockerfile` (installs Tesseract), `docker-compose.yml`, `.env.example`.
- The repository zip, Nidhi.zip.

## Current State & Open Questions

- **Built and working.** Every PS capability and all six test scenarios are implemented and automated; nothing functional is left for submission.
- **Not deployed yet.** There is no live URL. Render will build `deploy/Dockerfile`; the first build takes about 6–10 minutes, including about 3 minutes of seeding.
- **Not on GitHub yet.** The repo name and URL are to be decided, for example `prag-x/Nidhi`.
- **Deck placeholders.** Slide 6 still has red placeholders for the live link, demo video and GitHub link.
- **Theme.** Confirm the PS 26265 theme in the SIH portal; the title slide currently says "Smart Automation".
- **Demo video.** None recorded yet; a brag prompt is below.
- **Known limitations, stated in the README:**
  - bank verification is simulated;
  - OCR is measured on clean generated specimens, not on handwritten or stamped receipts;
  - the late-renewal model is modest;
  - bank turnaround KPIs come from the simulation's assumptions;
  - single sign-on and a real SMS/e-mail gateway are not wired (there is an outbox only);
  - Hindi coverage of the new strings is partial: untranslated strings fall back to English.
- **Competition.** At least 9 public PS 26265 repos exist. Several also have the three-source view, QR letters and OCR (details below).

## Next Steps

1. Unzip Nidhi.zip and upload it to a new GitHub repo via the web UI. Use the description below.
2. **Render:** *New + → Blueprint →* pick the repo. If the service name differs from `nidhi-signalnine`, set the build argument `PUBLIC_BASE_URL` (or edit `deploy/Dockerfile`) to the real URL, so letter QR codes resolve. Open `/api/health`, then sign in as `rb.head`.
3. Smoke-test on Render:
   - sign in as `kadamb`, lodge a renewal with `samples/kadamb_renewal_fdr.pdf`;
   - as `rb.head`, open it → *Verify with bank now* → *Accept*;
   - open a letter code at `/verify/<code>`;
   - as `admin`, run Integrity → tamper → verify → undo.
4. Record the demo video with the brag prompt below and upload it to YouTube (unlisted).
5. In `docs/ndeck/build.py` (or directly in PowerPoint), replace the slide 6 placeholders with the live URL, the video and GitHub, and confirm the Theme on slide 1. Export to PDF and upload the deck.
6. Paste the submission text below into the SIH form.
7. *Optional polish:* translate the new Hindi strings in `frontend/src/lib/hi.ts`; add more OCR test cases from real-looking scans.

**Run locally:**

```bash
cd backend
python -m venv .venv && .venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m app.cli seed --reset
.venv/bin/python -m uvicorn app.main:app --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

**Tests:**

```bash
cd backend && .venv/bin/python -m pytest -q
```

Browser tests: `pytest -q ../e2e`, with the app running and `NIDHI_E2E_URL` set if it isn't on port 5173.

---

## Submission text

**GitHub description (under 350 characters):**
Nidhi (निधि): AICTE Security Deposit & FDR Management Portal, SIH 2026 PS 26265. Reads FDR copies (PDF, scans, photos via offline OCR), compares declared vs document vs bank values, tracks maturity with reminders and escalation, maker-checker release with QR-verifiable letters, and a tamper-evident ledger. FastAPI + React.

**Idea title (under 100 characters):**
Nidhi: FDR portal that verifies every deposit with the bank and never lets one lapse

**Idea description:**
Nidhi is a single portal where institutions lodge their security deposits and FDRs, and the AICTE Regulation Bureau verifies, monitors and releases them.

- **Lodging:** the institution uploads the FDR copy (a PDF, a scan or a phone photo). The portal reads it offline, by OCR where needed, and fills in the form.
- **Three sources:** what the institution declared, what the document says and what the bank confirmed are kept side by side for every field, never merged.
- **Checks:** 17 automatic checks catch a short amount or validity, a missing lien, a wrong depositor, a bad IFSC, an altered copy and an FDR reused by another institution. Every held FDR is re-confirmed with its bank twice a year to catch closures.
- **Bank verification:** banks with an online service answer through a connector; for others the portal writes a verification letter and the officer records the reply.
- **Maturity:** a monitor sends reminders at 90, 60, 30 and 7 days. If a matured FDR is not renewed, it escalates to the RB head after 15 days and to the competent authority after 45. A model trained on each institution's renewal history flags who is likely to renew late.
- **Release:** the RB checks four conditions and recommends, the competent authority approves (never their own recommendation), and Accounts executes with a lien-release letter that any bank can verify by QR.
- **Oversight:** dashboards, a maturity calendar, eight reports, Ask in English and Hindi, and a hash-chained audit trail.

**Abstract / summary:**
AICTE holds security deposits and FDRs from institutions as part of approval and compliance. Today these are tracked through files, letters to banks and spreadsheets, so status is hard to keep accurate, verification is slow, and maturities can lapse unnoticed.

Nidhi digitises the full lifecycle: lodging with automatic document reading, verification with the issuing bank, discrepancy detection, maturity tracking with reminders and escalation, renewal chains, and authorised release. It keeps institution-declared and bank-confirmed information distinct, as the problem statement requires. Every action is sealed in a tamper-evident ledger, and every letter can be verified publicly.

Measured on 600 synthetic institutions:
- the checks caught all 450 planted faults with no false alarms;
- the reader got 100% of fields right on 300 digital FDRs, and 99.6% on 45 scanned ones;
- the late-renewal model reaches AUC 0.65 on institutions it never saw.

All six test scenarios in the problem statement are automated in 81 tests. Nidhi runs fully on AICTE's own server, with no external AI service, and is deployable as a single container.

**Technology bucket:** choose **AI/ML** first (OCR, late-renewal prediction, fuzzy matching). If the form allows more than one, add **Blockchain** (hash-chained tamper-evident ledger) and **Cloud Computing** (one-container deployment). Pick the closest options if the dropdown words them differently.

---

## Brag prompt: short demo video (about 75 s)

> Make a 75-second product demo of **Nidhi (निधि)**, an AICTE Security Deposit & FDR Management Portal (SIH 2026 PS 26265, Team SignalNine). App URL: `<RENDER_URL>`. Every password is `Demo@2026`. Calm, confident voice-over; on-screen captions; 1440×900; no music louder than the voice. Every scene below must be captured from the real app, never mocked.
>
> 1. **(0–6 s) Sign-in page.** Caption: "An FDR is security only if the bank says it is." Show the Declared / On the FDR copy / Bank confirmed specimen table.
> 2. **(6–18 s) Lodging, as `kadamb@nidhi.test`.** The desk shows an FDR maturing in about 26 days → *Lodge renewal* → drop `samples/kadamb_renewal_fdr.pdf` → "100% of the fields read", each field "Matches the FDR copy" → *Lodge*. An acknowledgement letter with a QR appears.
> 3. **(18–30 s) Verification, as `rb.head@nidhi.test`.** Open the new deposit → *Verify with bank now* → the "Confirmed by bank" column fills in with ticks → *Accept as security*.
> 4. **(30–40 s) Catching problems.** Search "Medhavi": the FDR-copy column shows ₹50,000 in red against ₹5,00,000 declared. Search "Tapasya Visakhapatnam": a critical "Same FDR already lodged" fraud signal, and the bank says the depositor is another trust.
> 5. **(40–50 s) Overview and maturity calendar.** The coloured KPI tiles; the 12-month maturity chart; click a month to list its FDRs. Caption: "Reminders at 90/60/30/7 days; escalation at 15 and 45 days after maturity."
> 6. **(50–60 s) Release, as `ms@nidhi.test`.** A recommended release with all four conditions ticked → *Approve release*. Then as `accounts@nidhi.test` → *Release lien and issue letter to bank*.
> 7. **(60–68 s) Public verification.** Open `/verify/<code>` signed out: "Genuine. Issued by the AICTE deposit portal."; upload an edited copy → "NOT the letter issued".
> 8. **(68–75 s) Proof page.** "Checks: precision 100%, recall 100% · OCR 99.6% · all on AICTE's server, no cloud AI." End card: "Nidhi · Team SignalNine · SIH 2026 PS 26265".

---

## Competition (public PS 26265 repos found on 30 Oct 2026)

| Repo | What it has | Compared with Nidhi |
|---|---|---|
| [Shash1704/aicte-fdr-portal](https://github.com/Shash1704/aicte-fdr-portal) | Node/Express + SQLite, three-way field check, OCR (tesseract.js), simulated bank, maker-checker, hash-chained audit, AES-encrypted files, 9 API test scenarios, live demo on GitHub Pages | The closest rival. We add measured accuracy, a trained model, QR letters, PostgreSQL, Hindi, and 81 tests |
| [kumudranjan6127-debug/fdr-intelligence-hub](https://github.com/kumudranjan6127-debug/fdr-intelligence-hub) | Next.js + Prisma/Postgres; Claimed / Extracted / Confirmed tags; NOC letters with QR and a public verify page; risk score as a fixed formula; optional Claude vision; live on Vercel | Strong concept. Its sign-in is a role switcher with no passwords, OCR is on the roadmap, and bank checks are mocked |
| [coderkartik7/SIH26265_FDR-Sentinel](https://github.com/coderkartik7/SIH26265_FDR-Sentinel) | FastAPI + React, Postgres/Redis/MinIO/Celery, Tesseract, forensics (ELA, PKI, Ed25519 QR), SHAP risk, 27 tests | Ambitious scope, but 2 commits and no live demo |
| [adityakumargupta27/sih-project-265](https://github.com/adityakumargupta27/sih-project-265) | Front end only, mock data, live on Vercel | We are full-stack |
| Others not yet reviewed | [Aashirwadaanand/fdr](https://github.com/Aashirwadaanand/fdr), [nishikadhankhar/koshsetu-sih](https://github.com/nishikadhankhar/koshsetu-sih), [JayachandraV16/FDR-Portal](https://github.com/JayachandraV16/FDR-Portal), [shree180/SIH26265](https://github.com/shree180/SIH26265), [dhina-514/aicte-fdr](https://github.com/dhina-514/aicte-fdr), [aisheechowdhury19801977-create/SecureFDR](https://github.com/aisheechowdhury19801977-create/SecureFDR) | — |

**Lean on in the pitch:**
1. Measured, re-runnable proof: precision, recall, OCR and model accuracy on the Proof page.
2. Re-confirming every held FDR with its bank, which catches FDRs closed at the branch.
3. A renewal-history model with reasons.
4. All six PS scenarios automated, on PostgreSQL and in a real browser.
5. Hindi and English with Ask.
6. Fully offline.
