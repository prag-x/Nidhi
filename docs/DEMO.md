# Demo walkthrough (about 12 minutes)

The demo data plants scenarios on fictional institutions so every capability can be shown live. When `python -m app.cli seed --reset` finishes it prints their reference numbers (they change with each seed). Every scenario is also easy to find with global search (**Ctrl+K**) by institution name.

Every account's password is `Demo@2026`; click an account on the sign-in page to sign in as it.

**Tip:** open two windows side by side, one as `kadamb` (the institution) and one as `rb.head`. Actions in one appear live in the other.

---

## 1. The institution's desk (1 min, `kadamb`)

*Kadamb Institute of Technology, Nashik* sees only its own deposits. One FDR matures in about 26 days and sits under **Renew before maturity**; the bell shows the reminder the portal sent (and **Administration → Outbox**, as `admin`, shows the e-mail and SMS).

## 2. New FDR submission and renewal (2 min, `kadamb`)

Open the maturing FDR and click **Lodge renewal**. The form is pre-filled from the FDR being replaced. Drop `samples/kadamb_renewal_fdr.pdf` into the box: the portal reads it, says *100% of the fields read*, and fills in the FDR number, amount, dates, depositor and lien. Each field shows *Matches the FDR copy*. The side panel shows what is required (demonstration norms). Click **Lodge**.

The deposit file opens with its reference and an **acknowledgement letter** with a QR code.

## 3. Verification: three sources, never mixed (2 min, `rb.head`)

Open the deposit just lodged. The table shows **Declared by institution**, **Read from FDR copy** and **Confirmed by bank**. Click **Verify with bank now**: Bharat National Bank answers through the (simulated) online service and the third column fills in, every field ticked. Click **Accept as security**. Back in the institution's window, the old FDR is now *Renewed* and the new one *Held*.

Now try the altered copy: as `kadamb`, lodge again with `samples/kadamb_renewal_fdr_altered.pdf`. The document says ₹1,50,000 where ₹15,00,000 was declared: **Uploaded document differs from what was declared**, and the cell turns red.

## 4. Discrepancies and fraud signals (2 min, `rb.head`)

Search for these institutions (scenario names as printed by the seed):

- **Medhavi Institute of Management Studies, Hyderabad**: *Document differs from declaration* (₹50,000 on the copy, ₹5,00,000 declared).
- **Late Shri Ramdas Kulkarni Memorial College of Engineering, Belagavi**: *Several discrepancies*: below the required amount, validity shorter than required, no lien marked. **Send for rectification** issues a rectification letter and moves it to the institution; **Accept** stays disabled while anything is open.
- **Tapasya College of Engineering, Visakhapatnam**: *Duplicate FDR*: the same FDR was already lodged by the Tapasya college in Vijayawada, run by a different trust. A **fraud signal** alert goes to the Bureau; the related deposit is linked.
- **Jagriti College of Pharmacy, Ahmedabad**: *Bank has no record*.
- **Saptarishi Polytechnic, Ludhiana**: accepted months ago, but the periodic re-confirmation found the bank now reports the FDR **closed**.

The head can **Waive with reason** (at least 10 characters, sealed in the history); a dealing officer cannot.

## 5. Validity tracking, escalation and the maturity calendar (1 min, `rb.head`)

**Maturity calendar**: each of the next 12 months, how many FDRs mature and how many already have a renewal lodged; red marks those likely to renew late. **Matured** lists FDRs past maturity with no replacement. *Nachiketa Institute of Engineering & Technology, Jaipur* matured over 45 days ago and is **escalated to the competent authority**.

**Udaan Institute of Management, Lucknow** has renewed late three times; its current FDR carries a high **late-renewal risk** with reasons (*earlier renewals arrived N days after maturity on average*). Its institution page draws each requirement's chain of FDRs, with the late handovers in red.

## 6. Authorised release (2 min)

- As `rb.officer1` or `rb.head`, open *Shri Vidyadeep College of Engineering, Pune* (**Release: awaiting recommendation**). Tick each of the four conditions; the portal shows what it found for each. **Recommend release**.
- As `ms` (Member Secretary), the desk shows **Releases awaiting your approval**. Approve. (Had the same person recommended, approval would be refused.)
- As `accounts`, **Release lien and issue letter to bank**. The deposit is *Released* and a lien-release letter is issued.

## 7. Verify a letter, publicly (1 min, no sign-in)

Open `/verify/<code>` from any letter (or scan its QR). It confirms AICTE issued it, shows the masked FDR and amount, and accepts an upload of the PDF: the original matches; a copy with one byte changed does not.

## 8. Overview, reports, Ask and Proof (1 min, `rb.head`)

- **Overview**: held, maturing, matured-unrenewed, pending, releases, renewed on time; maturity calendar, bank-wise and region-wise positions.
- **Reports**: eight reports, each in Excel, PDF and CSV.
- **Ask**: *How many FDRs above 10 lakh with Vindhya Bank?*, *90 दिन में परिपक्व होने वाली एफडीआर*.
- **Proof**: the discrepancy checks measured on 500 planted faults, the reader on 300 FDRs, the late-renewal model on institutions it never saw.

## 9. Integrity (1 min, `admin` then `auditor`)

**Integrity → Rewrite a bank-verification record** changes a stored history entry directly in the database. **Verify now** reports *Tampering detected* and names the deposit. **Undo the edit**, verify again: *Nothing has been altered*.
