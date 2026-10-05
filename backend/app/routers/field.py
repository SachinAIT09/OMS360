"""Outage tickets, crews, mutual aid and restoration/ETR publishing."""
import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from .. import bus, serial
from ..auth import current_user, require
from ..db import get_session
from ..models import (Crew, Facility, MutualAidRequest, Outage, PublishedEtr, StagingYard, StormEvent, User, Zone, utcnow)
from ..services import ops
from ..services.connector import next_number
from .events import get_event

router = APIRouter(tags=["field"])


def get_outage(s: Session, outage_id: int) -> Outage:
    o = s.get(Outage, outage_id)
    if not o:
        raise HTTPException(404, "Outage not found")
    return o


def _ops(fn, *a):
    try:
        return fn(*a)
    except ops.OpsError as e:
        raise HTTPException(409, str(e))


# ---------------------------------------------------------------- outages
SORTS = {"reported_at": Outage.reported_at, "customers": Outage.customers, "priority": Outage.priority, "status": Outage.status,
         "number": Outage.id, "zone": Outage.zone_id}


@router.get("/outages")
def list_outages(event_id: int | None = None, status: str | None = None, zone: str | None = None, priority: str | None = None,
                 q: str | None = None, open_only: bool = False, sort: str = "reported_at", desc: bool = True,
                 page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=500),
                 s: Session = Depends(get_session), _: User = Depends(current_user)):
    query = select(Outage)
    if event_id:
        query = query.where(Outage.event_id == event_id)
    if status:
        query = query.where(Outage.status.in_(status.split(",")))
    if open_only:
        query = query.where(Outage.status.in_(ops.OPEN))
    if zone:
        query = query.where(Outage.zone_id == zone)
    if priority:
        query = query.where(Outage.priority.in_(priority.split(",")))
    if q:
        like = f"%{q}%"
        query = query.where(or_(Outage.number.ilike(like), Outage.feeder_id.ilike(like), Outage.device.ilike(like)))
    total = s.scalar(select(func.count()).select_from(query.subquery()))
    col = SORTS.get(sort, Outage.reported_at)
    if sort == "priority":
        col = case((Outage.priority == "critical", 0), (Outage.priority == "high", 1), else_=2)
        desc = not desc
    rows = s.scalars(query.order_by(col.desc() if desc else col.asc()).offset((page - 1) * size).limit(size)).all()
    etrs = {}
    if event_id:
        e = s.get(StormEvent, event_id)
        if e:
            for z in ops.zone_etrs(s, e).values():
                etrs.update(z["tickets"])
    zones = {z.id: z.short for z in s.scalars(select(Zone)).all()}
    return {"total": total, "page": page, "size": size, "items": [serial.outage(o, etrs.get(o.id), zones.get(o.zone_id)) for o in rows]}


@router.get("/outages/export.csv")
def export_outages(event_id: int, s: Session = Depends(get_session), _: User = Depends(current_user)):
    rows = s.scalars(select(Outage).where(Outage.event_id == event_id).order_by(Outage.id)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["number", "zone", "feeder", "device", "cause", "damage", "customers", "priority", "status", "crew", "reported_at",
                "assigned_at", "restored_at", "etr_at"])
    for o in rows:
        w.writerow([o.number, o.zone_id, o.feeder_id, o.device, o.cause, o.damage, o.customers, o.priority, o.status,
                    o.crew.code if o.crew else "", o.reported_at, o.assigned_at or "", o.restored_at or "", o.etr_at or ""])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=outages-event-{event_id}.csv"})


@router.get("/outages/{outage_id}")
def outage_detail(outage_id: int, s: Session = Depends(get_session), _: User = Depends(current_user)):
    o = get_outage(s, outage_id)
    etr = None
    if o.event_id and o.status in ops.OPEN:
        e = s.get(StormEvent, o.event_id)
        etr = ops.zone_etrs(s, e).get(o.zone_id, {}).get("tickets", {}).get(o.id)
    fac = s.get(Facility, o.facility_id) if o.facility_id else None
    return {**serial.outage(o, etr), "facility": fac.name if fac else None, "job_hours": round(ops.job_hours(o), 1),
            "history": [serial.outage_event(h) for h in reversed(o.history)], "allowed": sorted(ops.TRANSITIONS[o.status])}


class OutageIn(BaseModel):
    event_id: int | None = None
    zone_id: str
    feeder_id: str
    device: str = ""
    cause: str = "unknown"
    damage: str = "unknown"
    customers: int = Field(ge=1, le=100000)
    priority: str = "normal"
    notes: str = ""


@router.post("/outages", status_code=201)
def create_outage(body: OutageIn, s: Session = Depends(get_session), user: User = Depends(require("outages.manage"))):
    z = s.get(Zone, body.zone_id)
    if not z:
        raise HTTPException(422, "Unknown zone")
    o = Outage(number=next_number(s), **body.model_dump(), source="field", lat=z.lat, lng=z.lng)
    s.add(o)
    s.flush()
    ops.log(s, o, "created", f"Created manually: {o.customers:,} customers on {o.feeder_id}", user.name)
    bus.audit(s, user.name, "outage.created", "outage", o.number, f"{o.number} {z.short}, {o.customers:,} customers", o.event_id)
    s.commit()
    bus.publish("outages")
    return serial.outage(o)


class OutagePatch(BaseModel):
    cause: str | None = None
    damage: str | None = None
    customers: int | None = Field(None, ge=1)
    priority: str | None = None
    notes: str | None = None


@router.patch("/outages/{outage_id}")
def update_outage(outage_id: int, body: OutagePatch, s: Session = Depends(get_session), user: User = Depends(require("outages.manage"))):
    o = get_outage(s, outage_id)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(o, k, v)
    if changes:
        if o.status == "reported" and ({"cause", "damage"} & changes.keys()):
            o.status = "assessed"
        ops.log(s, o, "update", "Updated " + ", ".join(f"{k} → {v}" for k, v in changes.items()), user.name)
    s.commit()
    bus.publish("outages")
    return outage_detail(o.id, s, user)


class AssignIn(BaseModel):
    crew_id: int


@router.post("/outages/{outage_id}/assign")
def assign(outage_id: int, body: AssignIn, s: Session = Depends(get_session), user: User = Depends(require("outages.manage"))):
    o = get_outage(s, outage_id)
    crew = s.get(Crew, body.crew_id)
    if not crew:
        raise HTTPException(404, "Crew not found")
    _ops(ops.assign, s, o, crew, user.name)
    bus.audit(s, user.name, "outage.assigned", "outage", o.number, f"{o.number} → {crew.code}", o.event_id)
    s.commit()
    bus.publish("outages")
    return outage_detail(o.id, s, user)


class TicketStatusIn(BaseModel):
    status: str
    note: str = ""


@router.post("/outages/{outage_id}/status")
def ticket_status(outage_id: int, body: TicketStatusIn, s: Session = Depends(get_session), user: User = Depends(require("outages.manage"))):
    o = get_outage(s, outage_id)
    _ops(ops.set_status, s, o, body.status, user.name, body.note)
    bus.audit(s, user.name, "outage.status", "outage", o.number, f"{o.number} → {body.status}", o.event_id)
    s.commit()
    bus.publish("outages")
    return outage_detail(o.id, s, user)


class EtrIn(BaseModel):
    etr_at: datetime


@router.post("/outages/{outage_id}/etr")
def set_etr(outage_id: int, body: EtrIn, s: Session = Depends(get_session), user: User = Depends(require("outages.manage"))):
    o = get_outage(s, outage_id)
    ops.override_etr(s, o, body.etr_at, user.name)
    s.commit()
    bus.publish("outages")
    return outage_detail(o.id, s, user)


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/outages/{outage_id}/notes")
def add_note(outage_id: int, body: NoteIn, s: Session = Depends(get_session), user: User = Depends(current_user)):
    o = get_outage(s, outage_id)
    ops.log(s, o, "note", body.text, user.name)
    s.commit()
    return outage_detail(o.id, s, user)


@router.post("/events/{event_id}/auto-dispatch")
def auto_dispatch(event_id: int, s: Session = Depends(get_session), user: User = Depends(require("outages.manage"))):
    e = get_event(s, event_id)
    n = ops.auto_dispatch(s, e, user.name)
    bus.audit(s, user.name, "outage.auto_dispatch", "storm_event", e.id, f"{n} tickets dispatched", e.id)
    s.commit()
    bus.publish("outages")
    return {"dispatched": n}


# ---------------------------------------------------------------- crews
@router.get("/crews")
def list_crews(status: str | None = None, kind: str | None = None, source: str | None = None, q: str | None = None,
               include_released: bool = False, s: Session = Depends(get_session), _: User = Depends(current_user)):
    kind_order = case((Crew.kind == "line", 0), (Crew.kind == "tree", 1), else_=2)
    query = select(Crew).order_by(Crew.source, kind_order, Crew.code)
    if status:
        query = query.where(Crew.status.in_(status.split(",")))
    elif not include_released:
        query = query.where(Crew.status != "released")
    if kind:
        query = query.where(Crew.kind == kind)
    if source:
        query = query.where(Crew.source == source)
    if q:
        query = query.where(or_(Crew.code.ilike(f"%{q}%"), Crew.company.ilike(f"%{q}%"), Crew.lead.ilike(f"%{q}%")))
    crews = s.scalars(query).all()
    work = {o.crew_id: o for o in s.scalars(select(Outage).where(Outage.status.in_(["assigned", "in_progress"]), Outage.crew_id.is_not(None))).all()}
    return [{**serial.crew(c), "current": {"id": work[c.id].id, "number": work[c.id].number, "zone": work[c.id].zone_id,
                                            "status": work[c.id].status} if c.id in work else None} for c in crews]


@router.get("/crews/summary")
def crews_summary(s: Session = Depends(get_session), _: User = Depends(current_user)):
    rows = s.execute(select(Crew.kind, Crew.source, Crew.status, func.count(), func.sum(Crew.size)).group_by(Crew.kind, Crew.source, Crew.status)).all()
    return [{"kind": k, "source": src, "status": st, "crews": n, "workers": int(w or 0)} for k, src, st, n, w in rows]


class CrewPatch(BaseModel):
    status: str


@router.patch("/crews/{crew_id}")
def update_crew(crew_id: int, body: CrewPatch, s: Session = Depends(get_session), user: User = Depends(require("crews.manage"))):
    c = s.get(Crew, crew_id)
    if not c:
        raise HTTPException(404, "Crew not found")
    if body.status not in ("available", "off_shift", "staged"):
        raise HTTPException(422, "Crews can be set available, staged or off shift. Assignment happens from a ticket.")
    if c.status in ("assigned", "working"):
        raise HTTPException(409, f"{c.code} is {c.status}; finish or reassign its ticket first.")
    c.status = body.status
    bus.audit(s, user.name, "crew.status", "crew", c.code, f"{c.code} → {body.status}")
    s.commit()
    bus.publish("crews")
    return serial.crew(c)


@router.get("/staging-yards")
def yards(s: Session = Depends(get_session), _: User = Depends(current_user)):
    counts = dict(s.execute(select(Crew.yard_id, func.sum(Crew.size)).where(Crew.status == "staged").group_by(Crew.yard_id)).all())
    return [{"id": y.id, "name": y.name, "lat": y.lat, "lng": y.lng, "capacity": y.capacity, "active": y.active,
             "staged_workers": int(counts.get(y.id) or 0)} for y in s.scalars(select(StagingYard)).all()]


# ---------------------------------------------------------------- mutual aid
@router.get("/mutual-aid")
def list_mutual_aid(event_id: int | None = None, s: Session = Depends(get_session), _: User = Depends(current_user)):
    q = select(MutualAidRequest).order_by(MutualAidRequest.id.desc())
    if event_id:
        q = q.where(MutualAidRequest.event_id == event_id)
    return [serial.mutual_aid(r) for r in s.scalars(q).all()]


class MutualAidIn(BaseModel):
    event_id: int
    company: str = Field(min_length=2)
    origin: str = ""
    kind: str = "line"
    workers: int = Field(ge=2, le=2000)
    eta: datetime | None = None


@router.post("/mutual-aid", status_code=201)
def request_mutual_aid(body: MutualAidIn, s: Session = Depends(get_session), user: User = Depends(require("mutual_aid.manage"))):
    get_event(s, body.event_id)
    r = MutualAidRequest(**body.model_dump(), requested_by=user.name)
    s.add(r)
    s.flush()
    bus.audit(s, user.name, "mutual_aid.requested", "mutual_aid", r.id, f"{r.workers} {r.kind} workers from {r.company}", r.event_id)
    s.commit()
    bus.publish("mutual_aid")
    return serial.mutual_aid(r)


MA_FLOW = {"requested": {"confirmed", "cancelled"}, "confirmed": {"en_route", "cancelled"}, "en_route": {"arrived"},
           "arrived": {"released"}, "released": set(), "cancelled": set()}


@router.post("/mutual-aid/{req_id}/status")
def mutual_aid_status(req_id: int, body: TicketStatusIn, s: Session = Depends(get_session),
                      user: User = Depends(require("mutual_aid.manage"))):
    r = s.get(MutualAidRequest, req_id)
    if not r:
        raise HTTPException(404, "Request not found")
    if body.status not in MA_FLOW[r.status]:
        raise HTTPException(409, f"Can't move from {r.status} to {body.status}.")
    detail = f"{r.company}: {r.status} → {body.status}"
    if body.status == "arrived":
        yard = s.scalars(select(StagingYard).order_by(StagingYard.capacity.desc())).first()
        n = ops.arrive_mutual_aid(s, r, yard.lat, yard.lng)
        detail += f" ({n} crews rostered at {yard.name})"
    elif body.status == "released":
        n = ops.release_mutual_aid(s, r)
        detail += f" ({n} crews released)"
    else:
        r.status = body.status
    bus.audit(s, user.name, "mutual_aid.status", "mutual_aid", r.id, detail, r.event_id)
    s.commit()
    bus.publish("mutual_aid")
    bus.publish("crews")
    return serial.mutual_aid(r)


# ---------------------------------------------------------------- restoration
@router.get("/events/{event_id}/restoration")
def restoration(event_id: int, s: Session = Depends(get_session), _: User = Depends(current_user)):
    e = get_event(s, event_id)
    from ..services.recommendations import latest_prediction
    pr = latest_prediction(s, e.id)
    return {"event": serial.event(e), "stats": ops.event_stats(s, e), "curve": ops.restoration_curve(s, e),
            "prediction": {"avg_eta_h": pr.result["avg_eta_h"], "p95_eta_h": pr.result["p95_eta_h"],
                           "zones": {z["id"]: z["eta_h"] for z in pr.result["zones"]}} if pr else None,
            "can_publish": e.status in ("active", "restoring")}


class PublishIn(BaseModel):
    zone_ids: list[str] | None = None  # None = every zone with open tickets


@router.post("/events/{event_id}/publish")
def publish(event_id: int, body: PublishIn, s: Session = Depends(get_session), user: User = Depends(require("etr.publish"))):
    e = get_event(s, event_id)
    if e.status not in ("active", "restoring"):
        raise HTTPException(409, "ETRs can be published while an event is Active or Restoring.")
    st = ops.event_stats(s, e)
    targets = body.zone_ids or [z["id"] for z in st["zones"] if z["open_tickets"]]
    existing = {p.zone_id for p in s.scalars(select(PublishedEtr).where(PublishedEtr.event_id == e.id)).all()}
    added = [z for z in targets if z not in existing]
    for z in added:
        s.add(PublishedEtr(event_id=e.id, zone_id=z, published_by=user.name))
    bus.audit(s, user.name, "etr.published", "storm_event", e.id, f"ETRs published for {len(added)} zones", e.id)
    s.commit()
    bus.publish("restoration")
    return {"published": len(added)}


@router.delete("/events/{event_id}/publish/{zone_id}")
def unpublish(event_id: int, zone_id: str, s: Session = Depends(get_session), user: User = Depends(require("etr.publish"))):
    row = s.get(PublishedEtr, (event_id, zone_id))
    if row:
        s.delete(row)
        bus.audit(s, user.name, "etr.unpublished", "storm_event", event_id, f"ETR unpublished for {zone_id}", event_id)
        s.commit()
        bus.publish("restoration")
    return {"ok": True}
