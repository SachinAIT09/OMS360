"""Storm event lifecycle."""
from sqlalchemy.orm import Session

from .. import bus
from ..models import StormEvent, utcnow

LIFECYCLE = ["monitoring", "preparing", "active", "restoring", "closed"]
ALLOWED = {
    "monitoring": {"preparing", "active", "closed"},
    "preparing": {"monitoring", "active", "closed"},
    "active": {"restoring"},
    "restoring": {"active", "closed"},
    "closed": set(),
}
LABELS = {"monitoring": "Monitoring", "preparing": "Preparing", "active": "Active", "restoring": "Restoring", "closed": "Closed"}


class LifecycleError(Exception):
    pass


def change_status(s: Session, e: StormEvent, status: str, user: str) -> None:
    if status not in ALLOWED.get(e.status, set()):
        raise LifecycleError(f"{e.name} can't move from {LABELS[e.status]} to {LABELS.get(status, status)}.")
    prev = e.status
    e.status = status
    now = utcnow()
    if status == "active" and not e.activated_at:
        e.activated_at = now
    if status == "restoring" and not e.restoring_at:
        e.restoring_at = now
    if status == "closed":
        e.closed_at = now
    bus.audit(s, user, "event.status", "storm_event", e.id, f"{e.name}: {LABELS[prev]} → {LABELS[status]}", e.id)
    bus.publish("events", id=e.id, status=status)
