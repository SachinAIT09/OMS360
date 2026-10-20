"""Circuit-level customer notifications.

When a circuit's ETR is published, customers on that circuit get an SMS with their own circuit's time and confidence.
While it stays published, any move of more than an hour sends an update, and when its last outage is restored they are
told power is back (once; a new outage on the circuit re-arms it). Every ETR told to customers is also kept
as an EtrSnapshot, which is what confidence calibration is measured on.
"""
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..data import UTILITY_SHORT
from ..fmt import fmt_dt
from ..models import EtrSnapshot, Message, NotificationRule, Outage, PublishedCircuitEtr, StormEvent, utcnow
from . import ops

TRIGGER = "circuit_etr"
RULE_NAME = "Circuit ETR published, moves by more than 1 hour, or power restored → SMS to customers on that circuit"
CHANGE_H = 1.0
SMS_REACH = 0.71  # share of customers with a mobile number on file
AUTHOR = "Automated — circuit ETR"


def ensure_rule(s: Session) -> None:
    if not s.scalars(select(NotificationRule).where(NotificationRule.trigger == TRIGGER)).first():
        s.add(NotificationRule(name=RULE_NAME, trigger=TRIGGER, channel="sms", enabled=True))


def _rule(s: Session) -> NotificationRule | None:
    return s.scalars(select(NotificationRule).where(NotificationRule.trigger == TRIGGER, NotificationRule.enabled.is_(True))).first()


def _send(s: Session, e: StormEvent, c: dict, body: str, rule: NotificationRule, customers: int | None = None) -> None:
    n = round((c["customers_out"] if customers is None else customers) * SMS_REACH)
    now = utcnow()
    s.add(Message(event_id=e.id, channel="sms", audience=f"circuit:{c['id']}", body=body, status="sent", ai_generated=False,
                  recipients=n, created_by=AUTHOR, approved_by="Pre-approved template", sent_at=now, created_at=now, updated_at=now))
    rule.sent_count += n


def _snapshot(s: Session, e: StormEvent, c: dict) -> None:
    if c["etr_at"]:
        s.add(EtrSnapshot(event_id=e.id, feeder_id=c["id"], at=utcnow(), etr_at=c["etr_at"], confidence=c["confidence"]))


def circuits_published(s: Session, e: StormEvent, circuits: list[dict]) -> int:
    """Called when circuit ETRs are published. Returns customers texted."""
    rule = _rule(s)
    sent = 0
    for c in circuits:
        _snapshot(s, e, c)
        if rule and c["etr_at"]:
            _send(s, e, c, f"{UTILITY_SHORT}: Estimated restoration for your circuit {c['id']} ({c['zone']}): {fmt_dt(c['etr_at'])}, "
                           f"{c['confidence']}% confidence. We'll text you if it changes by more than 1 hour. STOP to opt out.", rule)
            sent += round(c["customers_out"] * SMS_REACH)
    return sent


def watch(s: Session, e: StormEvent) -> int:
    """Re-check published circuits: text customers when an ETR moves by more than CHANGE_H, and once when the circuit's
    last outage is restored. Returns messages sent."""
    published = {p.feeder_id: p for p in s.scalars(select(PublishedCircuitEtr).where(PublishedCircuitEtr.event_id == e.id)).all()}
    if not published:
        return 0
    rule = _rule(s)
    updates = 0
    circuits = ops.network_etrs(s, e)["circuits"]
    still_out = {c["id"] for c in circuits}
    for fid, p in published.items():
        if fid in still_out or p.restored_at:
            continue
        restored = s.execute(select(func.count(Outage.id), func.sum(Outage.customers)).where(
            Outage.event_id == e.id, Outage.feeder_id == fid, Outage.status == "restored")).one()
        if not restored[0]:
            continue  # cancelled rather than restored: nothing to announce
        p.restored_at = utcnow()
        if rule:
            _send(s, e, {"id": fid}, f"{UTILITY_SHORT}: Power has been restored on your circuit {fid}. Still out? Reply OUT and we'll send a crew. "
                                     "STOP to opt out.", rule, customers=int(restored[1] or 0))
        updates += 1
    for c in circuits:
        p = published.get(c["id"])
        if p and p.restored_at:
            p.restored_at = None  # a new outage on a restored circuit: its customers hear about the new ETR below
            p.etr_at = None
        if not p or not c["etr_at"]:
            continue
        if p.etr_at is None:
            p.etr_at, p.confidence = c["etr_at"], c["confidence"]
            _snapshot(s, e, c)
            if rule:
                _send(s, e, c, f"{UTILITY_SHORT}: New outage on your circuit {c['id']} ({c['zone']}). Estimated restoration {fmt_dt(c['etr_at'])}, "
                               f"{c['confidence']}% confidence. STOP to opt out.", rule)
            updates += 1
            continue
        if abs(c["etr_at"] - p.etr_at) <= timedelta(hours=CHANGE_H):
            continue
        later = c["etr_at"] > p.etr_at
        p.etr_at, p.confidence = c["etr_at"], c["confidence"]
        _snapshot(s, e, c)
        if rule:
            _send(s, e, c, f"{UTILITY_SHORT} update for circuit {c['id']} ({c['zone']}): restoration is now expected "
                           f"{'later' if later else 'sooner'}, by {fmt_dt(c['etr_at'])} ({c['confidence']}% confidence). STOP to opt out.", rule)
        updates += 1
    return updates
