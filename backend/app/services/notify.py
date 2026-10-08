"""Circuit-level customer notifications.

When a circuit's ETR is published, customers on that circuit get an SMS with their own circuit's time and confidence.
While it stays published, any move of more than an hour sends an update. Every ETR told to customers is also kept
as an EtrSnapshot, which is what confidence calibration is measured on.
"""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..fmt import fmt_dt
from ..models import EtrSnapshot, Message, NotificationRule, PublishedCircuitEtr, StormEvent, utcnow
from . import ops

TRIGGER = "circuit_etr"
RULE_NAME = "Circuit ETR published or changes by more than 1 hour → SMS to customers on that circuit"
CHANGE_H = 1.0
SMS_REACH = 0.71  # share of customers with a mobile number on file
AUTHOR = "Automated — circuit ETR"


def ensure_rule(s: Session) -> None:
    if not s.scalars(select(NotificationRule).where(NotificationRule.trigger == TRIGGER)).first():
        s.add(NotificationRule(name=RULE_NAME, trigger=TRIGGER, channel="sms", enabled=True))


def _rule(s: Session) -> NotificationRule | None:
    return s.scalars(select(NotificationRule).where(NotificationRule.trigger == TRIGGER, NotificationRule.enabled.is_(True))).first()


def _send(s: Session, e: StormEvent, c: dict, body: str, rule: NotificationRule) -> None:
    n = round(c["customers_out"] * SMS_REACH)
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
            _send(s, e, c, f"Bayview: Estimated restoration for your circuit {c['id']} ({c['zone']}): {fmt_dt(c['etr_at'])}, "
                           f"{c['confidence']}% confidence. We'll text you if it changes by more than 1 hour. STOP to opt out.", rule)
            sent += round(c["customers_out"] * SMS_REACH)
    return sent


def watch(s: Session, e: StormEvent) -> int:
    """Re-check published circuits; text customers when an ETR moves by more than CHANGE_H. Returns updates sent."""
    published = {p.feeder_id: p for p in s.scalars(select(PublishedCircuitEtr).where(PublishedCircuitEtr.event_id == e.id)).all()}
    if not published:
        return 0
    rule = _rule(s)
    updates = 0
    for c in ops.network_etrs(s, e)["circuits"]:
        p = published.get(c["id"])
        if not p or not c["etr_at"] or not p.etr_at or abs(c["etr_at"] - p.etr_at) <= timedelta(hours=CHANGE_H):
            continue
        later = c["etr_at"] > p.etr_at
        p.etr_at, p.confidence = c["etr_at"], c["confidence"]
        _snapshot(s, e, c)
        if rule:
            _send(s, e, c, f"Bayview update for circuit {c['id']} ({c['zone']}): restoration is now expected "
                           f"{'later' if later else 'sooner'}, by {fmt_dt(c['etr_at'])} ({c['confidence']}% confidence). STOP to opt out.", rule)
        updates += 1
    return updates
