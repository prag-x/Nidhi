"""In-process publish/subscribe for live dashboard updates over Server-Sent Events.

Services publish from worker threads; subscribers are asyncio queues on the event loop.
A multi-worker deployment would swap this for Redis pub/sub behind the same two functions.
"""

import asyncio
import json
import logging
import threading
from dataclasses import dataclass, field

from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


@dataclass(eq=False)
class Subscriber:
    user_id: int
    unit_id: int | None
    is_global: bool
    institution_id: int | None = None   # institution users only ever receive events about their own institution
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=200))


class Broker:
    def __init__(self) -> None:
        self._subs: set[Subscriber] = set()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, sub: Subscriber) -> None:
        with self._lock:
            self._subs.add(sub)

    def unsubscribe(self, sub: Subscriber) -> None:
        with self._lock:
            self._subs.discard(sub)

    def publish(self, kind: str, data: dict, unit_ids: set[int] | None = None, user_ids: set[int] | None = None) -> None:
        """Send to everyone, or only to the given units/users (global users always receive)."""
        if self._loop is None:
            return
        message = json.dumps({"type": kind, "data": data}, default=str)
        with self._lock:
            targets = [s for s in self._subs if _wants(s, data, unit_ids, user_ids)]
        for sub in targets:
            try:
                self._loop.call_soon_threadsafe(_offer, sub.queue, message)
            except RuntimeError:  # loop closed during shutdown
                log.debug("event loop closed; dropping event")


def _wants(s: Subscriber, data: dict, unit_ids, user_ids) -> bool:
    if s.institution_id is not None:
        return data.get("institution_id") == s.institution_id
    return bool((unit_ids is None and user_ids is None) or s.is_global or (unit_ids and s.unit_id in unit_ids)
                or (user_ids and s.user_id in user_ids))


def _offer(queue: asyncio.Queue, message: str) -> None:
    try:
        queue.put_nowait(message)
    except asyncio.QueueFull:
        pass  # slow client; it will refetch on reconnect


broker = Broker()


# ---------------------------------------------------------------- publish after commit

_PENDING_KEY = "pending_events"


def queue_event(
    db: Session, kind: str, data: dict, unit_ids: set[int] | None = None, user_ids: set[int] | None = None
) -> None:
    """Publish once the surrounding transaction commits, so clients never refetch stale data."""
    db.info.setdefault(_PENDING_KEY, []).append((kind, data, unit_ids, user_ids))


@sa_event.listens_for(Session, "after_commit")
def _flush_events(session: Session) -> None:
    for kind, data, unit_ids, user_ids in session.info.pop(_PENDING_KEY, []):
        broker.publish(kind, data, unit_ids, user_ids)


@sa_event.listens_for(Session, "after_rollback")
def _drop_events(session: Session) -> None:
    session.info.pop(_PENDING_KEY, None)
