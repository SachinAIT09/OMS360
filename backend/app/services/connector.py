"""OMS / AMI integration connector.

Modes (Admin → Integrations):
  off      — no automatic intake; tickets are created by users or the API.
  sandbox  — emulates the utility's OMS/AMI and field mobile app for training and demos:
             • while an event is Active, smart-meter last-gasp events open outage tickets until
               the predicted impact is reached (spread over ~20 minutes);
             • while an event is Preparing, the outer rain bands keep a small stream of scattered
               outages coming, and routine dispatch keeps a few crews on them;
             • field crews accept assigned work and close it as they finish (time-compressed);
             • mutual-aid partners confirm, travel and arrive at staging yards.
A production deployment replaces this module with the utility's OMS adapter (MultiSpeak / REST).
"""
import asyncio
import logging
import random
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import bus
from ..db import SessionLocal, get_setting
from ..models import (Crew, Facility, Feeder, Message, MutualAidRequest, NotificationRule, Outage, StagingYard, StormEvent, Zone,
                      utcnow)
from . import ops
from .recommendations import latest_prediction

log = logging.getLogger("oms360.connector")
TICK_SECONDS = 4
INTAKE_MINUTES = 10
ACCEPT_AFTER_S = 15          # crew acknowledges assignment
SECONDS_PER_JOB_HOUR = 12    # time compression for field work in sandbox
BAND_OPEN_TARGET = 20        # Preparing: open tickets the outer bands keep in play
BAND_NEW_CHANCE = 0.25       # Preparing: chance per tick of a new ticket (~1 every 16 s) while below target
BAND_WORK_TARGET = 8         # Preparing: tickets routine dispatch keeps assigned / in progress
BAND_DISPATCH_CHANCE = 0.3   # Preparing: chance per tick of dispatching the oldest waiting ticket
OPEN = ("reported", "assessed", "assigned", "in_progress")
_rng = random.Random()


def next_number(s: Session) -> str:
    n = s.scalar(select(func.max(Outage.id))) or 0
    return f"OUT-{24000 + n + 1}"


def new_ticket(s: Session, e: StormEvent, zone: Zone, feeders: list[Feeder], mean_customers: float,
               facilities: dict[str, Facility], rng: random.Random = _rng, at=None) -> Outage:
    f = rng.choice(feeders)
    fac = facilities.get(f.id)
    surge = zone.coastal and rng.random() < 0.4
    cause = "surge" if surge else rng.choices(["wind", "tree", "equipment", "flooding"], [45, 40, 10, 5])[0]
    damage = rng.choices(["service", "conductor", "transformer", "pole"], [25, 35, 25, 15])[0]
    customers = max(1, int(mean_customers * rng.choice([0.05, 0.2, 0.5, 0.8, 1.2, 1.8, 3.0])))
    if damage == "service":
        customers = min(customers, rng.randint(1, 40))
    device = {"service": f"Service drop SD-{rng.randint(10000, 99999)}", "transformer": f"Transformer T-{rng.randint(1000, 9999)}",
              "conductor": f"Span {f.id}-{rng.randint(10, 400)}", "pole": f"Pole P-{rng.randint(10000, 99999)}"}[damage]
    priority = "critical" if fac and rng.random() < 0.6 else "high" if customers > 1500 else "normal"
    o = Outage(number=next_number(s), event_id=e.id, zone_id=zone.id, feeder_id=f.id, device=device, cause=cause,
               damage=damage if rng.random() < 0.7 else "unknown", customers=customers, priority=priority,
               facility_id=fac.id if fac and priority == "critical" else None,
               source=rng.choices(["AMI", "SCADA", "customer", "field"], [70, 10, 15, 5])[0],
               lat=zone.lat + rng.uniform(-0.05, 0.05), lng=zone.lng + rng.uniform(-0.05, 0.05),
               reported_at=at or utcnow())
    if at:
        o.reported_at = at
    s.add(o)
    s.flush()
    ops.log(s, o, "created", f"Opened from {o.source}: {customers:,} customers on {f.id}" + (f" — critical facility: {fac.name}" if o.facility_id else ""))
    return o


def _intake(s: Session, e: StormEvent) -> int:
    pr = latest_prediction(s, e.id)
    target = (pr.result["pred_total"] if pr else 40000 * max(1, e.category)) * 0.9
    affected = s.scalar(select(func.sum(Outage.customers)).where(Outage.event_id == e.id)) or 0
    if affected >= target:
        return 0
    zones = {z.id: z for z in s.scalars(select(Zone)).all()}
    weights = {zr["id"]: zr["pred"] for zr in pr.result["zones"]} if pr else {z: zones[z].customers * zones[z].vulnerability for z in zones}
    feeders: dict[str, list[Feeder]] = {}
    for f in s.scalars(select(Feeder)).all():
        feeders.setdefault(f.zone_id, []).append(f)
    facilities = {f.feeder_id: f for f in s.scalars(select(Facility)).all()}
    ticks = INTAKE_MINUTES * 60 / TICK_SECONDS
    expected_tickets = 260
    mean = target / expected_tickets
    n = max(1, round(expected_tickets / ticks + _rng.random()))
    created = []
    for _ in range(n):
        zid = _rng.choices(list(weights), list(weights.values()))[0]
        created.append(new_ticket(s, e, zones[zid], feeders[zid], mean, facilities))
    rule = s.scalars(select(NotificationRule).where(NotificationRule.trigger == "outage_detected", NotificationRule.enabled.is_(True))).first()
    if rule:
        rule.sent_count += sum(round(o.customers * 0.71) for o in created)
    return len(created)


def _outer_bands(s: Session, e: StormEvent) -> tuple[int, int]:
    """Pre-landfall trickle: scattered wind/tree outages plus routine dispatch, so a Preparing storm never goes quiet."""
    counts = dict(s.execute(select(Outage.status, func.count(Outage.id)).where(Outage.event_id == e.id, Outage.status.in_(OPEN))
                            .group_by(Outage.status)).all())
    created = dispatched = 0
    if sum(counts.values()) < BAND_OPEN_TARGET and _rng.random() < BAND_NEW_CHANCE:
        zones = s.scalars(select(Zone)).all()
        z = _rng.choices(zones, [z.customers * z.vulnerability * (1.6 if z.coastal else 1) for z in zones])[0]
        feeders = s.scalars(select(Feeder).where(Feeder.zone_id == z.id)).all()
        facilities = {f.feeder_id: f for f in s.scalars(select(Facility)).all()}
        o = new_ticket(s, e, z, feeders, 70, facilities)
        o.cause = _rng.choices(["wind", "tree", "equipment"], [45, 45, 10])[0]
        o.customers = min(o.customers, _rng.randint(8, 900))
        created = 1
        rule = s.scalars(select(NotificationRule).where(NotificationRule.trigger == "outage_detected", NotificationRule.enabled.is_(True))).first()
        if rule:
            rule.sent_count += round(o.customers * 0.71)
    if counts.get("assigned", 0) + counts.get("in_progress", 0) < BAND_WORK_TARGET and _rng.random() < BAND_DISPATCH_CHANCE:
        waiting = s.scalars(select(Outage).where(Outage.event_id == e.id, Outage.status.in_(["reported", "assessed"]))
                            .order_by(Outage.reported_at)).first()
        crews = s.scalars(select(Crew).where(Crew.kind == "line", Crew.status == "available")).all()
        if waiting and crews:
            ops.assign(s, waiting, _rng.choice(crews), "Routine dispatch")
            dispatched = 1
    return created, dispatched


def _field_progress(s: Session) -> int:
    now = utcnow()
    changed = 0
    for o in s.scalars(select(Outage).where(Outage.status == "assigned", Outage.assigned_at < now - timedelta(seconds=ACCEPT_AFTER_S))).all():
        ops.set_status(s, o, "in_progress", f"{o.crew.code if o.crew else 'Crew'} (mobile app)")
        changed += 1
    restored = 0
    for o in s.scalars(select(Outage).where(Outage.status == "in_progress")).all():
        if o.started_at and (now - o.started_at).total_seconds() >= ops.job_hours(o) * SECONDS_PER_JOB_HOUR:
            ops.set_status(s, o, "restored", f"{o.crew.code if o.crew else 'Crew'} (mobile app)", "power restored, AMI confirms")
            restored += o.customers
            changed += 1
    if restored:
        rule = s.scalars(select(NotificationRule).where(NotificationRule.trigger == "restored", NotificationRule.enabled.is_(True))).first()
        if rule:
            rule.sent_count += round(restored * 0.71)
    return changed


def _mutual_aid(s: Session) -> int:
    now = utcnow()
    changed = 0
    for r in s.scalars(select(MutualAidRequest).where(MutualAidRequest.status.in_(["requested", "confirmed", "en_route"]))).all():
        age = (now - r.requested_at).total_seconds()
        if r.status == "requested" and age > 20:
            r.status = "confirmed"; changed += 1
            bus.audit(s, r.company, "mutual_aid.confirmed", "mutual_aid", r.id, f"{r.company} confirmed {r.workers} {r.kind} workers", r.event_id)
        elif r.status == "confirmed" and age > 50:
            r.status = "en_route"; changed += 1
        elif r.status == "en_route" and age > 110:
            yard = s.scalars(select(StagingYard).order_by(StagingYard.capacity.desc())).first()
            ops.arrive_mutual_aid(s, r, yard.lat, yard.lng)
            bus.audit(s, r.company, "mutual_aid.arrived", "mutual_aid", r.id, f"{r.company} crews arrived at {yard.name}", r.event_id)
            changed += 1
    return changed


def _send_scheduled(s: Session) -> int:
    """Release approved messages whose scheduled time has come (runs in every mode)."""
    due = s.scalars(select(Message).where(Message.status == "scheduled", Message.scheduled_for <= utcnow())).all()
    for m in due:
        m.status, m.sent_at = "sent", utcnow()
        bus.audit(s, "Scheduler", "message.sent", "message", m.id, f"Scheduled {m.channel} message sent to {m.recipients:,} recipients", m.event_id)
    return len(due)


def tick() -> None:
    with SessionLocal() as s:
        if _send_scheduled(s):
            s.commit()
            bus.publish("messages")
        if get_setting(s, "connector_mode", "sandbox") != "sandbox":
            return
        created = 0
        for e in s.scalars(select(StormEvent).where(StormEvent.status == "active")).all():
            created += _intake(s, e)
        progressed = 0
        for e in s.scalars(select(StormEvent).where(StormEvent.status == "preparing")).all():
            c, d = _outer_bands(s, e)
            created, progressed = created + c, progressed + d
        progressed += _field_progress(s)
        ma = _mutual_aid(s)
        s.commit()
    if created or progressed:
        bus.publish("outages", created=created, updated=progressed)
    if ma:
        bus.publish("mutual_aid")
        bus.publish("crews")


async def run_forever() -> None:
    while True:
        try:
            await asyncio.to_thread(tick)
        except Exception:  # keep the connector alive; surface in logs
            log.exception("connector tick failed")
        await asyncio.sleep(TICK_SECONDS)
