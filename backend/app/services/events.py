"""Storm event lifecycle."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import bus
from ..models import Outage, StormEvent, utcnow

LIFECYCLE = ["monitoring", "preparing", "active", "restoring", "closed"]
ALLOWED = {
    "monitoring": {"preparing", "active", "closed"},
    "preparing": {"monitoring", "active", "closed"},
    "active": {"restoring"},
    "restoring": {"active", "closed"},
    "closed": set(),
}
OPEN_TICKETS = ("reported", "assessed", "assigned", "in_progress")
LABELS = {"monitoring": "Monitoring", "preparing": "Preparing", "active": "Active", "restoring": "Restoring", "closed": "Closed"}

RAIN = "Rain Event"
TORNADO = "Tornado"
EVENT_KINDS = ["Hurricane", "Tropical Storm", "Tropical Depression", TORNADO, "Severe Thunderstorm", "Winter Storm", RAIN]


def hazard(e: StormEvent) -> str:
    """How an event is modelled: "rain" (rainfall and flooding), "tornado" (EF rating and damage paths, circuit by circuit)
    or "wind" (category, wind field and landfall: hurricanes and the other wind storms)."""
    return "rain" if e.kind == RAIN else "tornado" if e.kind == TORNADO else "wind"


def is_rain(e: StormEvent) -> bool:
    """Rain events are modelled on rainfall and flooding instead of category, wind and landfall."""
    return e.kind == RAIN


def is_tornado(e: StormEvent) -> bool:
    return e.kind == TORNADO


def scale_label(e: StormEvent, category: int | None = None) -> str:
    """The intensity as people say it: "EF4" for tornadoes, "Cat 3" otherwise."""
    c = e.category if category is None else category
    return f"EF{c}" if is_tornado(e) else f"Cat {c}"


def impact_word(e: StormEvent) -> str:
    """What the impact time (landfall_at) means for this kind of event."""
    return {"rain": "rain onset", "tornado": "touchdown"}.get(hazard(e), "landfall")


class LifecycleError(Exception):
    pass


def change_status(s: Session, e: StormEvent, status: str, user: str) -> None:
    if status not in ALLOWED.get(e.status, set()):
        raise LifecycleError(f"{e.name} can't move from {LABELS[e.status]} to {LABELS.get(status, status)}.")
    if status == "closed":
        from .notify import watch
        watch(s, e)  # last restoration texts go out before the event is frozen
        open_n = s.scalar(select(func.count(Outage.id)).where(Outage.event_id == e.id, Outage.status.in_(OPEN_TICKETS)))
        if open_n:  # closing would orphan customers who are still out: no ETR, no updates, no restoration
            raise LifecycleError(f"{open_n} outage ticket{'s are' if open_n != 1 else ' is'} still open on {e.name}. "
                                 "Restore or cancel them before closing the event.")
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
