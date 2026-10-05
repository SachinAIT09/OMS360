"""Live operations: ticket workflow, crew dispatch and ETRs computed from real records.

ETR model
  job hours(ticket)  = base hours by damage type × damage multiplier by cause (surge 2.3×, flooding 1.8×)
  assigned ticket    → committed ETR = assignment time + travel + job hours
  unassigned queue   → per zone, ordered by priority then customers; position k finishes at
                       now + travel + (cumulative job hours ≤ k) ÷ effective crews in zone
  effective crews    = crews already working the zone + share of idle crews ∝ zone backlog
  zone ETR           = when the last open ticket in the zone is expected to be restored
"""
import math
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import bus
from ..models import Crew, Facility, MutualAidRequest, Outage, OutageEvent, PublishedEtr, StormEvent, Zone, utcnow

OPEN = ("reported", "assessed", "assigned", "in_progress")
JOB_HOURS = {"service": 1.5, "conductor": 3.0, "transformer": 4.0, "pole": 6.0, "none": 1.0, "unknown": 3.0}
CAUSE_MULT = {"surge": 2.3, "flooding": 1.8}
TRAVEL_H = 0.75
PRIORITY_RANK = {"critical": 0, "high": 1, "normal": 2}
TRANSITIONS = {
    "reported": {"assessed", "assigned", "cancelled"},
    "assessed": {"assigned", "cancelled"},
    "assigned": {"in_progress", "assessed", "restored"},
    "in_progress": {"restored", "assigned"},
    "restored": set(),
    "cancelled": set(),
}


class OpsError(Exception):
    pass


def job_hours(o: Outage) -> float:
    return JOB_HOURS.get(o.damage, 3.0) * CAUSE_MULT.get(o.cause, 1.0)


def log(s: Session, o: Outage, kind: str, text: str, user: str = "System") -> None:
    s.add(OutageEvent(outage_id=o.id, kind=kind, text=text, user_name=user))


# ------------------------------------------------------------------ ETR
def zone_etrs(s: Session, event: StormEvent, now: datetime | None = None) -> dict[str, dict]:
    now = now or utcnow()
    tickets = s.scalars(select(Outage).where(Outage.event_id == event.id, Outage.status.in_(OPEN))).all()
    crews = s.scalars(select(Crew).where(Crew.status.in_(["available", "staged", "assigned", "working"]))).all()
    idle = sum(1 for c in crews if c.status in ("available", "staged") and c.kind == "line")
    working_zone: dict[str, int] = defaultdict(int)
    for t in tickets:
        if t.crew_id and t.status in ("assigned", "in_progress"):
            working_zone[t.zone_id] += 1

    by_zone: dict[str, list[Outage]] = defaultdict(list)
    for t in tickets:
        by_zone[t.zone_id].append(t)
    backlog = {z: sum(job_hours(t) for t in ts if t.status in ("reported", "assessed")) for z, ts in by_zone.items()}
    total_backlog = sum(backlog.values()) or 1

    out: dict[str, dict] = {}
    for zid, ts in by_zone.items():
        eff = max(1.0, working_zone[zid] + idle * backlog[zid] / total_backlog)
        latest = now
        ticket_etr: dict[int, datetime] = {}
        for t in ts:
            if t.status in ("assigned", "in_progress"):
                etr = t.etr_at or (now + timedelta(hours=TRAVEL_H + job_hours(t)))
                ticket_etr[t.id] = etr
                latest = max(latest, etr)
        queue = sorted((t for t in ts if t.status in ("reported", "assessed")), key=lambda t: (PRIORITY_RANK[t.priority], -t.customers))
        cum = 0.0
        for t in queue:
            cum += job_hours(t)
            etr = t.etr_at if t.etr_override and t.etr_at else now + timedelta(hours=TRAVEL_H + cum / eff)
            ticket_etr[t.id] = etr
            latest = max(latest, etr)
        assessed = sum(1 for t in ts if t.status != "reported") / len(ts)
        out[zid] = {"etr_at": _round30(latest), "tickets": ticket_etr, "crews": working_zone[zid],
                    "confidence": int(min(95, 60 + 30 * assessed + (5 if idle else 0))),
                    "open": len(ts), "customers_out": sum(t.customers for t in ts)}
    return out


def _round30(d: datetime) -> datetime:
    secs = math.ceil(d.timestamp() / 1800) * 1800
    return datetime.fromtimestamp(secs, tz=d.tzinfo)


# ------------------------------------------------------------------ live stats
def event_stats(s: Session, event: StormEvent) -> dict:
    tickets = s.scalars(select(Outage).where(Outage.event_id == event.id)).all()
    zones = {z.id: z for z in s.scalars(select(Zone)).all()}
    crews = s.scalars(select(Crew)).all()
    published = {p.zone_id: p for p in s.scalars(select(PublishedEtr).where(PublishedEtr.event_id == event.id)).all()}
    etrs = zone_etrs(s, event)

    by_status: dict[str, int] = defaultdict(int)
    for t in tickets:
        by_status[t.status] += 1
    affected = sum(t.customers for t in tickets if t.status != "cancelled")
    out_now = sum(t.customers for t in tickets if t.status in OPEN)
    crew_status: dict[str, int] = defaultdict(int)
    workers = 0
    for c in crews:
        crew_status[c.status] += 1
        if c.status != "released" and c.kind == "line":
            workers += c.size

    zone_rows = []
    for z in zones.values():
        zt = [t for t in tickets if t.zone_id == z.id and t.status != "cancelled"]
        e = etrs.get(z.id)
        zone_rows.append({
            "id": z.id, "name": z.name, "short": z.short, "lat": z.lat, "lng": z.lng, "customers": z.customers,
            "coastal": z.coastal, "critical": z.critical, "medical": z.medical,
            "affected": sum(t.customers for t in zt), "customers_out": e["customers_out"] if e else 0,
            "open_tickets": e["open"] if e else 0, "crews": e["crews"] if e else 0,
            "etr_at": e["etr_at"] if e else None, "confidence": e["confidence"] if e else None,
            "published": z.id in published, "published_at": published[z.id].published_at if z.id in published else None,
            "pct_out": round((e["customers_out"] if e else 0) / z.customers, 4),
        })
    etr_list = [z["etr_at"] for z in zone_rows if z["etr_at"]]
    return {
        "tickets_total": len(tickets), "tickets_by_status": dict(by_status),
        "open_tickets": sum(by_status[k] for k in OPEN), "unassigned": by_status["reported"] + by_status["assessed"],
        "customers_affected": affected, "customers_out": out_now,
        "restored_pct": round(1 - out_now / affected, 4) if affected else 0.0,
        "crews_by_status": dict(crew_status), "line_workers_on_hand": workers,
        "critical_open": sum(1 for t in tickets if t.priority == "critical" and t.status in OPEN),
        "zones": zone_rows, "last_etr_at": max(etr_list) if etr_list else None,
        "published_zones": len(published),
    }


def restoration_curve(s: Session, event: StormEvent) -> dict:
    """Actual cumulative restoration from ticket timestamps, hourly since activation."""
    tickets = s.scalars(select(Outage).where(Outage.event_id == event.id, Outage.status != "cancelled")).all()
    start = event.activated_at or event.created_at
    if not tickets:
        return {"start": start, "points": []}
    end = max([t.restored_at or utcnow() for t in tickets] + [utcnow() if event.status != "closed" else start])
    hours = max(1, math.ceil((end - start).total_seconds() / 3600))
    step = max(1, hours // 48)
    points = []
    for h in range(0, hours + step, step):
        at = start + timedelta(hours=h)
        affected = sum(t.customers for t in tickets if t.reported_at <= at)
        restored = sum(t.customers for t in tickets if t.restored_at and t.restored_at <= at)
        points.append({"hour": h, "at": at, "out": affected - restored, "restored_pct": round(restored / affected, 4) if affected else 0})
    return {"start": start, "points": points}


# ------------------------------------------------------------------ ticket actions
def set_status(s: Session, o: Outage, status: str, user: str, note: str = "") -> None:
    if status == o.status:
        return
    if status not in TRANSITIONS[o.status]:
        raise OpsError(f"Can't move a ticket from {o.status} to {status}.")
    now = utcnow()
    prev = o.status
    o.status = status
    if status == "in_progress":
        o.started_at = now
        if o.crew:
            o.crew.status = "working"
    if status == "restored":
        o.restored_at = now
        if o.crew:
            o.crew.status = "available"
            o.crew.lat, o.crew.lng = o.lat, o.lng
    if status == "assessed" and prev in ("assigned",) and o.crew:
        o.crew.status = "available"
        o.crew_id = None
    if status == "cancelled" and o.crew:
        o.crew.status = "available"
        o.crew_id = None
    log(s, o, "status", f"Status {prev.replace('_', ' ')} → {status.replace('_', ' ')}" + (f": {note}" if note else ""), user)


def assign(s: Session, o: Outage, crew: Crew, user: str) -> None:
    if o.status not in ("reported", "assessed", "assigned"):
        raise OpsError(f"Ticket is {o.status}; it can't be assigned.")
    if crew.status not in ("available", "staged") and crew.id != o.crew_id:
        raise OpsError(f"{crew.code} is {crew.status} and can't take new work.")
    if o.crew and o.crew.id != crew.id:
        o.crew.status = "available"
    now = utcnow()
    o.crew_id, o.crew = crew.id, crew
    o.status = "assigned"
    o.assigned_at = now
    if not o.etr_override:
        o.etr_at = _round30(now + timedelta(hours=TRAVEL_H + job_hours(o)))
    crew.status = "assigned"
    log(s, o, "assigned", f"Assigned to {crew.code} ({crew.company}, {crew.size} workers). Committed ETR set.", user)


def override_etr(s: Session, o: Outage, etr: datetime, user: str) -> None:
    o.etr_at, o.etr_override = etr, True
    log(s, o, "etr", f"ETR manually set to {etr.isoformat()}", user)


def auto_dispatch(s: Session, event: StormEvent, user: str, limit: int = 200) -> int:
    """Greedy dispatch: highest-priority unassigned tickets get the nearest idle line crew."""
    queue = s.scalars(select(Outage).where(Outage.event_id == event.id, Outage.status.in_(["reported", "assessed"]))).all()
    queue = sorted(queue, key=lambda t: (PRIORITY_RANK[t.priority], -t.customers))[:limit]
    idle = s.scalars(select(Crew).where(Crew.status.in_(["available", "staged"]), Crew.kind == "line")).all()
    n = 0
    for t in queue:
        if not idle:
            break
        crew = min(idle, key=lambda c: (c.lat - t.lat) ** 2 + (c.lng - t.lng) ** 2)
        idle.remove(crew)
        assign(s, t, crew, f"{user} (auto-dispatch)")
        n += 1
    return n


def critical_facility_for(s: Session, zone_id: str, feeder_id: str) -> Facility | None:
    return s.scalars(select(Facility).where(Facility.feeder_id == feeder_id)).first()


def arrive_mutual_aid(s: Session, req: MutualAidRequest, yard_lat: float, yard_lng: float) -> int:
    """Turns an arrived mutual-aid request into rostered crews."""
    size = 4 if req.kind == "line" else 3
    count = max(1, req.workers // size)
    prefix = "".join(w[0] for w in req.company.split()[:2]).upper()
    existing = s.scalars(select(Crew).where(Crew.mutual_aid_id == req.id)).all()
    for i in range(len(existing), count):
        s.add(Crew(code=f"MA-{prefix}-{req.id:02d}{i + 1:02d}", kind=req.kind, company=req.company, source="mutual_aid",
                   size=size, status="staged", lat=yard_lat + (i % 7) * 0.004, lng=yard_lng + (i // 7) * 0.004,
                   mutual_aid_id=req.id, lead=f"Foreman {i + 1}"))
    req.status, req.arrived_at = "arrived", utcnow()
    bus.publish("crews")
    return count


def release_mutual_aid(s: Session, req: MutualAidRequest) -> int:
    crews = s.scalars(select(Crew).where(Crew.mutual_aid_id == req.id, Crew.status.in_(["available", "staged"]))).all()
    for c in crews:
        c.status = "released"
    req.status, req.released_at = "released", utcnow()
    return len(crews)
