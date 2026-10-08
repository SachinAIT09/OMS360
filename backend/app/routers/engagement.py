"""Customer communications, Jarvis, public outage map, live stream, search and reference data."""
import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from .. import bus, serial, weather
from ..auth import current_user, current_user_query, require
from ..data import SAMPLE_ADDRESSES, address_feeder
from ..db import get_session, get_setting
from ..models import (ChatConversation, ChatMessage, Crew, Facility, Feeder, Message, NotificationRule, Outage, PublishedEtr, StagingYard, StormEvent,
                      User, Zone, utcnow)
from ..services import comms, ops
from ..services import jarvis as jarvis_svc
from ..services.context import comms_context
from .events import get_event

router = APIRouter()


# ---------------------------------------------------------------- reference & search
@router.get("/reference", tags=["reference"])
def reference(s: Session = Depends(get_session), _: User = Depends(current_user)):
    zones = s.scalars(select(Zone)).all()
    return {
        "zones": [{"id": z.id, "code": z.code, "name": z.name, "short": z.short, "lat": z.lat, "lng": z.lng, "customers": z.customers,
                   "water_customers": z.water_customers, "vulnerability": z.vulnerability, "coastal": z.coastal, "critical": z.critical,
                   "medical": z.medical} for z in zones],
        "facilities": [{"id": f.id, "name": f.name, "kind": f.kind, "type": f.type, "lat": f.lat, "lng": f.lng, "zone_id": f.zone_id,
                        "feeder_id": f.feeder_id, "backup": f.backup} for f in s.scalars(select(Facility)).all()],
        "yards": [{"id": y.id, "name": y.name, "lat": y.lat, "lng": y.lng, "capacity": y.capacity, "active": y.active}
                  for y in s.scalars(select(StagingYard)).all()],
        "feeders": [{"id": fid, "zone_id": zid} for fid, zid in s.execute(select(Feeder.id, Feeder.zone_id).order_by(Feeder.id)).all()],
        "total_customers": sum(z.customers for z in zones), "total_water": sum(z.water_customers for z in zones),
        "channels": comms.CHANNELS, "purposes": comms.PURPOSES,
    }


@router.get("/search", tags=["reference"])
def search(q: str, s: Session = Depends(get_session), _: User = Depends(current_user)):
    like = f"%{q}%"
    out = [{"type": "outage", "id": o.id, "label": o.number, "sub": f"{o.zone_id.upper()} · {o.customers:,} customers · {o.status}"}
           for o in s.scalars(select(Outage).where(or_(Outage.number.ilike(like), Outage.feeder_id.ilike(like))).limit(6)).all()]
    out += [{"type": "crew", "id": c.id, "label": c.code, "sub": f"{c.company} · {c.status}"}
            for c in s.scalars(select(Crew).where(or_(Crew.code.ilike(like), Crew.lead.ilike(like))).limit(5)).all()]
    out += [{"type": "event", "id": e.id, "label": e.name, "sub": e.status} for e in s.scalars(select(StormEvent).where(StormEvent.name.ilike(like)).limit(4)).all()]
    return out


# ---------------------------------------------------------------- messages
@router.get("/messages", tags=["communications"])
def list_messages(event_id: int | None = None, status: str | None = None, s: Session = Depends(get_session), _: User = Depends(current_user)):
    q = select(Message).order_by(Message.id.desc())
    if event_id:
        q = q.where(Message.event_id == event_id)
    if status:
        q = q.where(Message.status.in_(status.split(",")))
    return [serial.message(m) for m in s.scalars(q.limit(300)).all()]


@router.get("/messages/stats", tags=["communications"])
def message_stats(event_id: int, s: Session = Depends(get_session), _: User = Depends(current_user)):
    rows = s.execute(select(Message.status, func.count(), func.sum(Message.recipients)).where(Message.event_id == event_id).group_by(Message.status)).all()
    by = {st: {"count": n, "recipients": int(r or 0)} for st, n, r in rows}
    rules = s.scalars(select(NotificationRule)).all()
    return {"by_status": by, "automated_sent": sum(r.sent_count for r in rules)}


@router.get("/comms/audiences", tags=["communications"])
def audiences(event_id: int | None = None, s: Session = Depends(get_session), _: User = Depends(current_user)):
    out = 0
    if event_id:
        out = ops.event_stats(s, get_event(s, event_id))["customers_out"]
    return comms.audiences(s, out, s.get(StormEvent, event_id) if event_id else None)


class DraftIn(BaseModel):
    event_id: int
    channel: str
    purpose: str | None = None


@router.post("/messages/ai-draft", tags=["communications"])
def ai_draft(body: DraftIn, s: Session = Depends(get_session), _: User = Depends(require("messages.create"))):
    e = get_event(s, body.event_id)
    if body.channel not in comms.CHANNELS:
        raise HTTPException(422, "Unknown channel")
    purpose = body.purpose or comms.default_purpose(e)
    if purpose not in comms.PURPOSES:
        raise HTTPException(422, "Unknown purpose")
    return comms.draft(e, body.channel, purpose, comms_context(s, e)) | {"purpose": purpose}


class MessageIn(BaseModel):
    event_id: int | None = None
    channel: str
    audience: str = "all"
    subject: str = ""
    body: str = Field(min_length=1, max_length=5000)
    ai_generated: bool = False
    scheduled_for: datetime | None = None
    submit: bool = False


def _recipients(s: Session, channel: str, audience: str, event_id: int | None) -> int:
    out = ops.event_stats(s, s.get(StormEvent, event_id))["customers_out"] if event_id and audience == "out" else 0
    e = s.get(StormEvent, event_id) if event_id else None
    aud = {a["id"]: a for a in comms.audiences(s, out, e if audience.startswith("circuit") else None)}.get(audience)
    if not aud:
        raise HTTPException(422, "Unknown audience")
    return comms.recipients(channel, aud["count"])


@router.post("/messages", status_code=201, tags=["communications"])
def create_message(body: MessageIn, s: Session = Depends(get_session), user: User = Depends(require("messages.create"))):
    if body.channel not in comms.CHANNELS:
        raise HTTPException(422, "Unknown channel")
    if body.channel == "x" and len(body.body) > 280:
        raise HTTPException(422, "Posts on X are limited to 280 characters.")
    m = Message(event_id=body.event_id, channel=body.channel, audience=body.audience, subject=body.subject, body=body.body,
                ai_generated=body.ai_generated, scheduled_for=body.scheduled_for, created_by=user.name,
                recipients=_recipients(s, body.channel, body.audience, body.event_id), status="pending" if body.submit else "draft")
    s.add(m)
    s.flush()
    bus.audit(s, user.name, "message.created", "message", m.id, f"{comms.CHANNELS[m.channel]} to {m.audience} ({m.status})", m.event_id)
    s.commit()
    bus.publish("messages")
    return serial.message(m)


class MessagePatch(BaseModel):
    subject: str | None = None
    body: str | None = None
    audience: str | None = None
    scheduled_for: datetime | None = None


def _get_msg(s: Session, mid: int) -> Message:
    m = s.get(Message, mid)
    if not m:
        raise HTTPException(404, "Message not found")
    return m


@router.patch("/messages/{mid}", tags=["communications"])
def update_message(mid: int, body: MessagePatch, s: Session = Depends(get_session), user: User = Depends(require("messages.create"))):
    m = _get_msg(s, mid)
    if m.status not in ("draft", "pending", "rejected"):
        raise HTTPException(409, f"A {m.status} message can't be edited.")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    if body.audience:
        m.recipients = _recipients(s, m.channel, m.audience, m.event_id)
    if m.status == "rejected":
        m.status = "draft"
    s.commit()
    bus.publish("messages")
    return serial.message(m)


def _transition(mid: int, s: Session, user: User, allowed_from: tuple, to: str, reason: str = ""):
    m = _get_msg(s, mid)
    if m.status not in allowed_from:
        raise HTTPException(409, f"Message is {m.status}.")
    if to == "approved":
        m.approved_by = user.name
        if m.scheduled_for and m.scheduled_for > utcnow():
            m.status = "scheduled"
        else:
            m.status, m.sent_at = "sent", utcnow()
    else:
        m.status = to
        if to == "rejected":
            m.reject_reason = reason
    bus.audit(s, user.name, f"message.{m.status}", "message", m.id,
              f"{comms.CHANNELS[m.channel]} to {m.audience}" + (f" — {m.recipients:,} recipients" if m.status == "sent" else "") +
              (f": {reason}" if reason else ""), m.event_id)
    s.commit()
    bus.publish("messages")
    return serial.message(m)


@router.post("/messages/{mid}/submit", tags=["communications"])
def submit(mid: int, s: Session = Depends(get_session), user: User = Depends(require("messages.create"))):
    return _transition(mid, s, user, ("draft", "rejected"), "pending")


@router.post("/messages/{mid}/approve", tags=["communications"])
def approve(mid: int, s: Session = Depends(get_session), user: User = Depends(require("messages.approve"))):
    return _transition(mid, s, user, ("pending",), "approved")


class RejectIn(BaseModel):
    reason: str = Field("", max_length=200)


@router.post("/messages/{mid}/reject", tags=["communications"])
def reject(mid: int, body: RejectIn, s: Session = Depends(get_session), user: User = Depends(require("messages.approve"))):
    return _transition(mid, s, user, ("pending",), "rejected", body.reason)


@router.delete("/messages/{mid}", tags=["communications"])
def delete_message(mid: int, s: Session = Depends(get_session), user: User = Depends(require("messages.create"))):
    m = _get_msg(s, mid)
    if m.status in ("sent", "scheduled"):
        raise HTTPException(409, "Sent or scheduled messages can't be deleted.")
    s.delete(m)
    s.commit()
    bus.publish("messages")
    return {"ok": True}


@router.get("/notification-rules", tags=["communications"])
def rules(s: Session = Depends(get_session), _: User = Depends(current_user)):
    return [{"id": r.id, "name": r.name, "trigger": r.trigger, "channel": r.channel, "enabled": r.enabled, "sent_count": r.sent_count}
            for r in s.scalars(select(NotificationRule).order_by(NotificationRule.id)).all()]


class RuleIn(BaseModel):
    enabled: bool


@router.patch("/notification-rules/{rid}", tags=["communications"])
def toggle_rule(rid: int, body: RuleIn, s: Session = Depends(get_session), user: User = Depends(require("messages.approve"))):
    r = s.get(NotificationRule, rid)
    if not r:
        raise HTTPException(404, "Rule not found")
    r.enabled = body.enabled
    bus.audit(s, user.name, "rule.toggled", "notification_rule", r.id, f"{r.name}: {'on' if r.enabled else 'off'}")
    s.commit()
    return {"ok": True}


# ---------------------------------------------------------------- Jarvis
class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    event_id: int | None = None
    conversation_id: int | None = None  # omitted: latest conversation; 0: start a new one


class SaveIn(BaseModel):
    saved: bool


async def _weather(s: Session) -> dict:
    return await weather.current(get_setting(s, "openweather_key") or weather.env_key())


def _conversation(s: Session, user: User, conversation_id: int | None) -> ChatConversation | None:
    """The requested conversation (must be the user's), or their most recent one; 0 means a new, empty conversation."""
    if conversation_id == 0:
        return None
    if conversation_id is not None:
        c = s.get(ChatConversation, conversation_id)
        if not c or c.user_id != user.id:
            raise HTTPException(404, "Conversation not found")
        return c
    return s.scalars(select(ChatConversation).where(ChatConversation.user_id == user.id)
                     .order_by(ChatConversation.updated_at.desc(), ChatConversation.id.desc())).first()


def _chat_row(r: ChatMessage) -> dict:
    return {"role": r.role, "id": r.id, "saved": r.saved, **r.payload}


@router.get("/jarvis/messages", tags=["jarvis"])
def chat(event_id: int | None = None, conversation_id: int | None = None, s: Session = Depends(get_session), user: User = Depends(current_user)):
    c = _conversation(s, user, conversation_id)
    rows = s.scalars(select(ChatMessage).where(ChatMessage.conversation_id == c.id).order_by(ChatMessage.id)).all() if c else []
    e = s.get(StormEvent, event_id) if event_id else None
    return [{"role": "jarvis", "id": 0, **jarvis_svc.greeting(user.name, e)}] + [_chat_row(r) for r in rows]


@router.post("/jarvis/ask", tags=["jarvis"])
async def ask(body: AskIn, s: Session = Depends(get_session), user: User = Depends(current_user)):
    e = s.get(StormEvent, body.event_id) if body.event_id else None
    c = _conversation(s, user, body.conversation_id)
    wx = await _weather(s)
    reply = await asyncio.to_thread(_answer, body.question, e.id if e else None, wx)
    now = utcnow()
    if not c:
        c = ChatConversation(user_id=user.id, title=body.question.strip()[:120], created_at=now)
        s.add(c)
        s.flush()
    c.updated_at = now
    s.add(ChatMessage(user_id=user.id, conversation_id=c.id, role="user", payload={"text": body.question}))
    answer = ChatMessage(user_id=user.id, conversation_id=c.id, role="jarvis", payload=reply)
    s.add(answer)
    s.commit()
    return {**reply, "id": answer.id, "saved": False, "conversation_id": c.id}


@router.get("/jarvis/conversations", tags=["jarvis"])
def conversations(s: Session = Depends(get_session), user: User = Depends(current_user)):
    counts = dict(s.execute(select(ChatMessage.conversation_id, func.count(ChatMessage.id))
                            .where(ChatMessage.user_id == user.id, ChatMessage.role == "user").group_by(ChatMessage.conversation_id)).all())
    rows = s.scalars(select(ChatConversation).where(ChatConversation.user_id == user.id)
                     .order_by(ChatConversation.updated_at.desc(), ChatConversation.id.desc()).limit(100)).all()
    return [{"id": c.id, "title": c.title, "created_at": c.created_at, "updated_at": c.updated_at, "questions": counts.get(c.id, 0)} for c in rows]


@router.delete("/jarvis/conversations/{conversation_id}", tags=["jarvis"])
def delete_conversation(conversation_id: int, s: Session = Depends(get_session), user: User = Depends(current_user)):
    c = _conversation(s, user, conversation_id)
    s.execute(delete(ChatMessage).where(ChatMessage.conversation_id == c.id))
    s.delete(c)
    s.commit()
    return {"ok": True}


@router.get("/jarvis/saved", tags=["jarvis"])
def saved_answers(s: Session = Depends(get_session), user: User = Depends(current_user)):
    rows = s.scalars(select(ChatMessage).where(ChatMessage.user_id == user.id, ChatMessage.saved.is_(True)).order_by(ChatMessage.id.desc())).all()
    out = []
    for r in rows:
        q = s.scalars(select(ChatMessage).where(ChatMessage.conversation_id == r.conversation_id, ChatMessage.role == "user",
                                                ChatMessage.id < r.id).order_by(ChatMessage.id.desc())).first()
        out.append({**_chat_row(r), "conversation_id": r.conversation_id, "question": q.payload.get("text") if q else None, "created_at": r.created_at})
    return out


@router.put("/jarvis/messages/{message_id}/saved", tags=["jarvis"])
def save_answer(message_id: int, body: SaveIn, s: Session = Depends(get_session), user: User = Depends(current_user)):
    m = s.get(ChatMessage, message_id)
    if not m or m.user_id != user.id or m.role != "jarvis":
        raise HTTPException(404, "Answer not found")
    m.saved = body.saved
    s.commit()
    return {"id": m.id, "saved": m.saved}


def _answer(question: str, event_id: int | None, wx: dict) -> dict:
    from ..db import SessionLocal
    with SessionLocal() as s:
        e = s.get(StormEvent, event_id) if event_id else None
        if e:
            from ..services.recommendations import refresh
            refresh(s, e)
        return jarvis_svc.answer(s, question, e, wx)


@router.delete("/jarvis/messages", tags=["jarvis"])
def clear_chat(s: Session = Depends(get_session), user: User = Depends(current_user)):
    s.execute(delete(ChatMessage).where(ChatMessage.user_id == user.id))
    s.execute(delete(ChatConversation).where(ChatConversation.user_id == user.id))
    s.commit()
    return {"ok": True}


# ---------------------------------------------------------------- public outage map (no sign-in)
def _public_event(s: Session) -> StormEvent | None:
    """The event customers see: the newest one with live outages, else the newest one being prepared for."""
    for statuses in (["active", "restoring"], ["preparing", "monitoring"]):
        e = s.scalars(select(StormEvent).where(StormEvent.status.in_(statuses)).order_by(StormEvent.created_at.desc())).first()
        if e:
            return e
    return None


@router.get("/public/outage-map", tags=["public"])
def public_map(s: Session = Depends(get_session)):
    e = _public_event(s)
    if not e:
        return {"event": None, "zones": [], "circuits": [], "customers_out": 0, "restored_pct": None, "sample_addresses": [a for a, _ in SAMPLE_ADDRESSES]}
    st = ops.event_stats(s, e)
    return {
        "event": {"name": e.name, "status": e.status, "landfall_at": e.landfall_at},
        "customers_out": st["customers_out"], "restored_pct": st["restored_pct"] if st["customers_affected"] else None,
        "zones": [{"id": z["id"], "short": z["short"], "lat": z["lat"], "lng": z["lng"], "customers": z["customers"],
                   "customers_out": z["customers_out"], "pct_out": z["pct_out"],
                   "etr_at": z["etr_at"] if z["published"] else None} for z in st["zones"]],
        "circuits": _public_circuits(s, e),
        "sample_addresses": [a for a, _ in SAMPLE_ADDRESSES],
    }


def _public_circuits(s: Session, e: StormEvent) -> list[dict]:
    routes = {f.id: f.route or [] for f in s.scalars(select(Feeder)).all()}
    return [{**{k: c[k] for k in ("id", "zone", "substation", "lat", "lng", "customers_out", "etr_at", "confidence")}, "route": routes.get(c["id"], [])}
            for c in ops.network_etrs(s, e)["circuits"] if c["published"]]


@router.get("/public/lookup", tags=["public"])
def public_lookup(address: str, s: Session = Depends(get_session)):
    a = address.lower().strip()
    zid = next((z for addr, z in SAMPLE_ADDRESSES if a and (a == addr.lower() or a in addr.lower())), None)
    zones = s.scalars(select(Zone)).all()
    if not zid:
        zid = next((z.id for z in zones if z.short.lower() in a), None)
    if not zid:
        raise HTTPException(404, "We couldn't find that address in the Bayview service area.")
    zone = s.get(Zone, zid)
    e = _public_event(s)
    shown = next((x for x, z in SAMPLE_ADDRESSES if z == zid and (a == x.lower() or a in x.lower())), None) \
        or next((x for x, z in SAMPLE_ADDRESSES if z == zid), address)
    feeder = address_feeder(shown, list(s.scalars(select(Feeder.id).where(Feeder.zone_id == zid))))
    base = {"zone": zone.short, "address": shown, "circuit": feeder}
    if not e or e.status in ("monitoring", "preparing"):
        return base | {"status": "no_outage", "event": e.name if e else None}
    circuit = next((c for c in ops.network_etrs(s, e)["circuits"] if c["id"] == feeder), None)
    if circuit and circuit["published"]:
        return base | {"status": "etr", "level": "circuit", "event": e.name, "etr_at": circuit["etr_at"], "crews": circuit["crews"],
                       "confidence": circuit["confidence"]}
    z = next(z for z in ops.event_stats(s, e)["zones"] if z["id"] == zid)
    if not z["customers_out"]:
        return base | {"status": "restored" if z["affected"] else "no_outage", "event": e.name}
    if z["published"]:
        return base | {"status": "etr", "level": "zone", "event": e.name, "etr_at": z["etr_at"], "crews": z["crews"], "confidence": z["confidence"]}
    return base | {"status": "confirmed", "event": e.name}


# ---------------------------------------------------------------- live updates (SSE)
@router.get("/stream", tags=["live"])
async def stream(request: Request, _: User = Depends(current_user_query)):
    q = bus.subscribe()

    async def gen():
        try:
            yield "event: hello\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
