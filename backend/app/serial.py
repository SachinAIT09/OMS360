"""Entity → JSON helpers (kept explicit so the API contract is easy to read)."""
from .auth import ROLES, permissions_for
from .models import (AuditLog, Crew, Message, MutualAidRequest, Outage, OutageEvent, Recommendation, StormEvent, Task,
                     User)


def user(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "title": u.title, "role": u.role, "role_label": ROLES[u.role],
            "active": u.active, "last_login_at": u.last_login_at, "permissions": permissions_for(u.role)}


def event(e: StormEvent) -> dict:
    return {"id": e.id, "name": e.name, "kind": e.kind, "source": e.source, "nhc_id": e.nhc_id, "status": e.status,
            "category": e.category, "max_wind_mph": e.max_wind_mph, "pressure_mb": e.pressure_mb, "lat": e.lat, "lng": e.lng,
            "movement": e.movement, "landfall_at": e.landfall_at, "track": e.track or [], "notes": e.notes,
            "created_at": e.created_at, "activated_at": e.activated_at, "restoring_at": e.restoring_at, "closed_at": e.closed_at}


def crew(c: Crew) -> dict:
    return {"id": c.id, "code": c.code, "kind": c.kind, "company": c.company, "source": c.source, "size": c.size,
            "status": c.status, "lead": c.lead, "lat": c.lat, "lng": c.lng, "yard_id": c.yard_id, "mutual_aid_id": c.mutual_aid_id}


def outage(o: Outage, etr=None, zone_name: str | None = None) -> dict:
    return {"id": o.id, "number": o.number, "event_id": o.event_id, "zone_id": o.zone_id, "zone": zone_name or (o.zone.short if o.zone else o.zone_id),
            "feeder_id": o.feeder_id, "device": o.device, "cause": o.cause, "damage": o.damage, "customers": o.customers,
            "priority": o.priority, "facility_id": o.facility_id, "status": o.status, "source": o.source, "lat": o.lat, "lng": o.lng,
            "crew": {"id": o.crew.id, "code": o.crew.code, "company": o.crew.company} if o.crew else None,
            "reported_at": o.reported_at, "assigned_at": o.assigned_at, "started_at": o.started_at, "restored_at": o.restored_at,
            "etr_at": o.etr_at or etr, "etr_committed": bool(o.etr_at), "etr_override": o.etr_override, "notes": o.notes}


def outage_event(h: OutageEvent) -> dict:
    return {"id": h.id, "at": h.at, "kind": h.kind, "text": h.text, "user": h.user_name}


def mutual_aid(r: MutualAidRequest) -> dict:
    return {"id": r.id, "event_id": r.event_id, "company": r.company, "origin": r.origin, "kind": r.kind, "workers": r.workers,
            "status": r.status, "eta": r.eta, "cost_per_worker_day": r.cost_per_worker_day, "requested_by": r.requested_by,
            "requested_at": r.requested_at, "arrived_at": r.arrived_at, "released_at": r.released_at}


def recommendation(r: Recommendation) -> dict:
    return {"id": r.id, "event_id": r.event_id, "key": r.key, "priority": r.priority, "title": r.title, "detail": r.detail,
            "impact": r.impact, "why": r.why, "status": r.status, "created_at": r.created_at, "decided_by": r.decided_by,
            "decided_at": r.decided_at, "outcome": r.outcome}


def message(m: Message) -> dict:
    return {"id": m.id, "event_id": m.event_id, "channel": m.channel, "audience": m.audience, "subject": m.subject, "body": m.body,
            "status": m.status, "ai_generated": m.ai_generated, "recipients": m.recipients, "created_by": m.created_by,
            "approved_by": m.approved_by, "reject_reason": m.reject_reason, "scheduled_for": m.scheduled_for, "sent_at": m.sent_at,
            "created_at": m.created_at, "updated_at": m.updated_at}


def task(t: Task) -> dict:
    return {"id": t.id, "event_id": t.event_id, "title": t.title, "owner_role": t.owner_role, "status": t.status,
            "due_at": t.due_at, "created_at": t.created_at, "done_at": t.done_at}


def audit(a: AuditLog) -> dict:
    return {"id": a.id, "at": a.at, "user": a.user_name, "action": a.action, "entity": a.entity, "entity_id": a.entity_id,
            "event_id": a.event_id, "detail": a.detail}
