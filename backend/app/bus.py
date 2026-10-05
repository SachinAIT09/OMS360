"""Audit trail + in-process event bus that feeds the /api/stream SSE endpoint.

Services run in worker threads (sync endpoints) or the connector task, so publishing is
thread-safe: each subscriber owns an asyncio queue on the server's event loop.
"""
import asyncio
import json
import threading
from datetime import datetime

from sqlalchemy.orm import Session

from .models import AuditLog

_subs: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
_lock = threading.Lock()


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    with _lock:
        _subs.append((asyncio.get_running_loop(), q))
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    with _lock:
        _subs[:] = [x for x in _subs if x[1] is not q]


def publish(kind: str, **data) -> None:
    """kind = resource that changed (outages, crews, messages, events, ...)."""
    payload = json.dumps({"type": kind, **data}, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o))
    with _lock:
        subs = list(_subs)
    for loop, q in subs:
        try:
            loop.call_soon_threadsafe(_put, q, payload)
        except RuntimeError:  # loop closed
            pass


def _put(q: asyncio.Queue, payload: str) -> None:
    if not q.full():
        q.put_nowait(payload)


def audit(s: Session, user_name: str, action: str, entity: str, entity_id="", detail: str = "", event_id: int | None = None,
          notify: bool = True) -> None:
    s.add(AuditLog(user_name=user_name, action=action, entity=entity, entity_id=str(entity_id), detail=detail, event_id=event_id))
    if notify:
        publish("activity", action=action, entity=entity, detail=detail, user=user_name)
