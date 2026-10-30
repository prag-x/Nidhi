"""Tamper-evident instrument history.

Each event stores sha256(previous hash + canonical JSON of the event). Editing or deleting any
past event breaks every hash after it, which `verify_chain` detects.
"""

import hashlib
import json
from datetime import UTC

from ..models import Instrument, InstrumentEvent

GENESIS = "0" * 64


def _utc(dt):
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def event_payload(ev: InstrumentEvent) -> dict:
    return {
        "instrument_id": ev.instrument_id,
        "seq": ev.seq,
        "event_type": ev.event_type,
        "occurred_at": (
            _utc(ev.occurred_at).isoformat(timespec="microseconds") if ev.occurred_at else None
        ),
        "actor_user_id": ev.actor_user_id,
        "actor_label": ev.actor_label,
        "from_status": ev.from_status,
        "to_status": ev.to_status,
        "remarks": ev.remarks,
        "meta": ev.meta,
    }


def compute_hash(prev_hash: str, ev: InstrumentEvent) -> str:
    canonical = json.dumps(event_payload(ev), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256((prev_hash + canonical).encode()).hexdigest()


def seal(ev: InstrumentEvent, prev_hash: str) -> None:
    ev.prev_hash = prev_hash
    ev.hash = compute_hash(prev_hash, ev)


def verify_chain(inst: Instrument) -> dict:
    prev = GENESIS
    for ev in sorted(inst.events, key=lambda e: e.seq):
        if ev.prev_hash != prev or compute_hash(prev, ev) != ev.hash:
            return {"valid": False, "events": len(inst.events), "broken_at_seq": ev.seq, "head": None}
        prev = ev.hash
    return {"valid": True, "events": len(inst.events), "broken_at_seq": None, "head": prev}


# ---------------------------------------------------------------- system ledger (one chain for everything)

LEDGER_GENESIS = hashlib.sha256(b"NIDHI-AICTE-LEDGER-GENESIS").hexdigest()


def _norm(value):
    return json.loads(json.dumps(value, default=str, ensure_ascii=False)) if value is not None else None


def entry_payload(e) -> dict:
    return {
        "seq": e.seq,
        "at": _utc(e.at).isoformat(timespec="microseconds") if e.at else None,
        "user_id": e.user_id,
        "action": e.action,
        "entity_type": e.entity_type,
        "entity_id": e.entity_id,
        "ip": e.ip,
        "details": _norm(e.details),
    }


def entry_hash(prev_hash: str, e) -> str:
    canonical = json.dumps(entry_payload(e), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256((prev_hash + canonical).encode()).hexdigest()


def _advance_head(db) -> tuple[int, str]:
    """Reserve the next sequence number. The UPDATE takes a write lock (SQLite) / row lock (PostgreSQL),
    so concurrent requests are serialised and the chain cannot fork."""
    from sqlalchemy import insert, update

    from ..models import LedgerHead

    row = db.execute(
        update(LedgerHead).where(LedgerHead.id == 1).values(seq=LedgerHead.seq + 1)
        .returning(LedgerHead.seq, LedgerHead.hash)
    ).first()
    if row is None:
        db.execute(insert(LedgerHead).values(id=1, seq=0, hash=LEDGER_GENESIS))
        return _advance_head(db)
    return row[0], row[1]


def append(db, entry) -> None:
    """Seal an AuditLog entry into the chain and add it to the session."""
    from sqlalchemy import update

    from ..db import utcnow
    from ..models import LedgerHead

    seq, prev = _advance_head(db)
    entry.seq = seq
    entry.at = entry.at or utcnow()
    entry.details = _norm(entry.details)
    entry.prev_hash = prev
    entry.hash = entry_hash(prev, entry)
    db.execute(update(LedgerHead).where(LedgerHead.id == 1).values(hash=entry.hash))
    db.add(entry)


def ledger_event(db, ev: InstrumentEvent) -> None:
    from ..models import AuditLog

    append(db, AuditLog(user_id=ev.actor_user_id, action="instrument_event", entity_type="instrument",
                        entity_id=str(ev.instrument_id),
                        details={"event_seq": ev.seq, "event_type": ev.event_type, "event_hash": ev.hash}))


def anchor(db, note: str | None = None, user=None):
    from sqlalchemy import select

    from ..models import LedgerAnchor, LedgerHead

    head = db.get(LedgerHead, 1)
    if head is None or head.seq == 0:
        return None
    latest = db.scalar(select(LedgerAnchor).order_by(LedgerAnchor.id.desc()).limit(1))
    if latest is not None and latest.seq == head.seq and user is None:
        return latest  # nothing new since the last checkpoint
    a = LedgerAnchor(seq=head.seq, hash=head.hash, note=note, created_by_id=user.id if user else None)
    db.add(a)
    db.flush()
    return a


def verify_ledger(db) -> dict:
    """Walk the whole system ledger and every instrument history; report the first break, if any."""
    from sqlalchemy import select

    from ..db import utcnow
    from ..models import AuditLog, LedgerAnchor, LedgerHead

    started = utcnow()
    db.expire_all()  # always read what is in the database now, never cached objects
    event_hashes = {(iid, seq): (h, eid) for eid, iid, seq, h in db.execute(
        select(InstrumentEvent.id, InstrumentEvent.instrument_id, InstrumentEvent.seq, InstrumentEvent.hash))}
    referenced: set[tuple[int, int]] = set()
    prev, expected, checked, first_break = LEDGER_GENESIS, 1, 0, None
    by_seq: dict[int, str] = {}
    for e in db.scalars(select(AuditLog).where(AuditLog.seq.is_not(None)).order_by(AuditLog.seq)).yield_per(5000):
        checked += 1
        by_seq[e.seq] = e.hash
        if first_break is None:
            if e.seq != expected:
                first_break = {"seq": expected, "kind": "MISSING",
                               "reason": f"Ledger entry #{expected} is missing; entries were deleted."}
            elif e.prev_hash != prev:
                first_break = {"seq": e.seq, "kind": "RELINKED",
                               "reason": f"Ledger entry #{e.seq} does not link to the previous entry; it was re-ordered."}
            elif entry_hash(e.prev_hash, e) != e.hash:
                first_break = {"seq": e.seq, "kind": "MODIFIED", "action": e.action, "entity": f"{e.entity_type}:{e.entity_id}",
                               "reason": f"Ledger entry #{e.seq} ({e.action}) was modified after it was written."}
        if e.action == "instrument_event" and e.details:
            key = (int(e.entity_id), int(e.details.get("event_seq", 0)))
            referenced.add(key)
            found = event_hashes.get(key)
            if first_break is None and found is None:
                first_break = {"seq": e.seq, "kind": "EVENT_DELETED", "instrument_id": key[0],
                               "reason": f"Instrument #{key[0]} history entry {key[1]} sealed in the ledger no longer exists."}
            elif first_break is None and found[0] != e.details.get("event_hash"):
                first_break = {"seq": e.seq, "kind": "EVENT_MODIFIED", "instrument_id": key[0],
                               "reason": f"Instrument #{key[0]} history entry {key[1]} differs from its sealed copy."}
        prev, expected = e.hash, e.seq + 1
    unledgered = [k for k in event_hashes if k not in referenced]
    head = db.get(LedgerHead, 1)
    if first_break is None and head is not None and checked and (head.seq != expected - 1 or head.hash != prev):
        first_break = {"seq": head.seq, "kind": "TRUNCATED", "reason": "The latest ledger entries were removed."}
    anchors = []
    for a in db.scalars(select(LedgerAnchor).order_by(LedgerAnchor.seq)):
        ok = by_seq.get(a.seq) == a.hash
        anchors.append({"seq": a.seq, "hash": a.hash, "at": a.at, "note": a.note, "ok": ok})
        if not ok and first_break is None:
            first_break = {"seq": a.seq, "kind": "ANCHOR_MISMATCH",
                           "reason": f"Ledger entry #{a.seq} no longer matches the checkpoint published on "
                                     f"{a.at:%d %b %Y}; the ledger was rebuilt."}
    # per-instrument chains
    from sqlalchemy.orm import selectinload

    broken = []
    instruments_checked = 0
    for inst in db.scalars(select(Instrument).options(selectinload(Instrument.events))).yield_per(1000):
        instruments_checked += 1
        r = verify_chain(inst)
        if not r["valid"]:
            broken.append({"instrument_id": inst.id, "ref_no": inst.ref_no, "broken_at_seq": r["broken_at_seq"]})
    return {
        "valid": first_break is None and not broken and not unledgered,
        "ledger_entries": checked,
        "head_seq": head.seq if head else 0,
        "head_hash": head.hash if head else LEDGER_GENESIS,
        "first_break": first_break,
        "instruments_checked": instruments_checked,
        "broken_instruments": broken[:20],
        "unledgered_events": len(unledgered),
        "anchors": anchors[-12:],
        "anchors_total": len(anchors),
        "verified_at": utcnow(),
        "seconds": round((utcnow() - started).total_seconds(), 2),
    }
