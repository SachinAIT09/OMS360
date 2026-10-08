"""Reports, administration (users, zones, integrations, audit) and weather."""
import statistics

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import bus, serial, weather
from ..auth import ROLES, current_user, hash_password, require
from ..db import DEMO_ADMIN_EMAILS, get_session, get_setting, set_setting
from ..models import (AuditLog, Crew, Message, MutualAidRequest, NotificationRule, Outage, StormEvent, User, Zone)
from ..services import ops
from ..services.recommendations import latest_prediction
from .events import get_event

router = APIRouter()


# ---------------------------------------------------------------- demo
@router.post("/demo/refresh", tags=["platform"])
def demo_refresh(s: Session = Depends(get_session), _: User = Depends(current_user)):
    """Called when the app loads: in sandbox (demo) mode, tops the demo storm back up to a full set of sample data."""
    if get_setting(s, "connector_mode", "sandbox") != "sandbox":
        return {"outages": 0, "messages": 0}
    from ..seed import refresh_demo
    added = refresh_demo(s)
    s.commit()
    if added["outages"]:
        bus.publish("outages", created=added["outages"])
    if added["messages"]:
        bus.publish("messages")
    return added


# ---------------------------------------------------------------- reports
@router.get("/reports/events", tags=["reports"])
def report_events(s: Session = Depends(get_session), _: User = Depends(current_user)):
    out = []
    for e in s.scalars(select(StormEvent).order_by(StormEvent.created_at.desc())).all():
        out.append(_summary(s, e))
    return out


def _summary(s: Session, e: StormEvent) -> dict:
    tickets = s.scalars(select(Outage).where(Outage.event_id == e.id, Outage.status != "cancelled")).all()
    restored = [t for t in tickets if t.restored_at]
    affected = sum(t.customers for t in tickets)
    durations = [(t.restored_at - t.reported_at).total_seconds() / 3600 for t in restored]
    cmi = sum(t.customers * (t.restored_at - t.reported_at).total_seconds() / 60 for t in restored)
    errs = [abs((t.restored_at - t.etr_at).total_seconds()) / 3600 for t in restored if t.etr_at]
    ma = s.scalars(select(MutualAidRequest).where(MutualAidRequest.event_id == e.id, MutualAidRequest.status != "cancelled")).all()
    msgs = s.execute(select(func.count(Message.id), func.sum(Message.recipients)).where(Message.event_id == e.id, Message.status == "sent")).one()
    pr = latest_prediction(s, e.id)
    return {
        "event": serial.event(e) | {"track": None}, "tickets": len(tickets), "customers_affected": affected,
        "predicted": pr.result["pred_total"] if pr else None,
        "prediction_error_pct": round((affected - pr.result["pred_total"]) / pr.result["pred_total"] * 100, 1) if pr and affected and e.status == "closed" else None,
        "restored_tickets": len(restored), "avg_restore_h": round(statistics.mean(durations), 1) if durations else None,
        "median_restore_h": round(statistics.median(durations), 1) if durations else None,
        "customer_minutes": round(cmi), "saidi_min": round(cmi / 692000, 1),
        "etr_mae_h": round(statistics.mean(errs), 2) if errs else None,
        "etr_within_2h_pct": round(sum(1 for x in errs if x <= 2) / len(errs) * 100, 1) if errs else None,
        "mutual_aid_workers": sum(r.workers for r in ma), "messages_sent": msgs[0] or 0, "message_recipients": int(msgs[1] or 0),
        "crews_used": len({t.crew_id for t in tickets if t.crew_id}),
    }


@router.get("/reports/events/{event_id}", tags=["reports"])
def report_event(event_id: int, s: Session = Depends(get_session), _: User = Depends(current_user)):
    e = get_event(s, event_id)
    tickets = s.scalars(select(Outage).where(Outage.event_id == e.id, Outage.status != "cancelled")).all()
    by_zone, by_cause, by_crew = {}, {}, {}
    zones = {z.id: z.short for z in s.scalars(select(Zone)).all()}
    for t in tickets:
        bz = by_zone.setdefault(t.zone_id, {"zone": zones[t.zone_id], "tickets": 0, "customers": 0, "hours": []})
        bz["tickets"] += 1
        bz["customers"] += t.customers
        if t.restored_at:
            bz["hours"].append((t.restored_at - t.reported_at).total_seconds() / 3600)
        by_cause[t.cause] = by_cause.get(t.cause, 0) + 1
        if t.crew_id:
            by_crew[t.crew_id] = by_crew.get(t.crew_id, 0) + 1
    channels = s.execute(select(Message.channel, func.count(), func.sum(Message.recipients)).where(Message.event_id == e.id, Message.status == "sent")
                         .group_by(Message.channel)).all()
    crews = {c.id: c for c in s.scalars(select(Crew)).all()}
    top_crews = sorted(by_crew.items(), key=lambda kv: -kv[1])[:10]
    return {
        "summary": _summary(s, e),
        "zones": [{"zone": v["zone"], "tickets": v["tickets"], "customers": v["customers"],
                   "avg_restore_h": round(statistics.mean(v["hours"]), 1) if v["hours"] else None} for v in sorted(by_zone.values(), key=lambda v: -v["customers"])],
        "causes": [{"cause": k, "tickets": v} for k, v in sorted(by_cause.items(), key=lambda kv: -kv[1])],
        "channels": [{"channel": c, "messages": n, "recipients": int(r or 0)} for c, n, r in channels],
        "crews": [{"code": crews[cid].code, "company": crews[cid].company, "tickets": n} for cid, n in top_crews if cid in crews],
        "curve": ops.restoration_curve(s, e),
        "etr_accuracy": ops.etr_accuracy(s, e),
    }


@router.get("/reports/calibration", tags=["reports"])
def report_calibration(event_id: int | None = None, s: Session = Depends(get_session), _: User = Depends(current_user)):
    """Circuit ETR confidence: promised vs. actual share restored within ±2 h, by confidence band."""
    from ..services import calibration
    return calibration.report(s, event_id)


# ---------------------------------------------------------------- users
class UserIn(BaseModel):
    email: str = Field(min_length=5, max_length=120)
    name: str = Field(min_length=2, max_length=80)
    title: str = ""
    role: str
    password: str = Field(min_length=6, max_length=100)


@router.get("/admin/users", tags=["admin"])
def users(s: Session = Depends(get_session), _: User = Depends(require("admin"))):
    return [serial.user(u) for u in s.scalars(select(User).order_by(User.id)).all()]


@router.post("/admin/users", status_code=201, tags=["admin"])
def create_user(body: UserIn, s: Session = Depends(get_session), admin: User = Depends(require("admin"))):
    if body.role not in ROLES:
        raise HTTPException(422, "Unknown role")
    if s.scalars(select(User).where(User.email == body.email.lower())).first():
        raise HTTPException(409, "A user with that email already exists.")
    u = User(email=body.email.lower(), name=body.name, title=body.title, role=body.role, password_hash=hash_password(body.password))
    s.add(u)
    s.flush()
    bus.audit(s, admin.name, "user.created", "user", u.id, f"{u.name} ({ROLES[u.role]})")
    s.commit()
    return serial.user(u)


class UserPatch(BaseModel):
    name: str | None = None
    title: str | None = None
    role: str | None = None
    active: bool | None = None
    password: str | None = Field(None, min_length=6)


@router.patch("/admin/users/{uid}", tags=["admin"])
def update_user(uid: int, body: UserPatch, s: Session = Depends(get_session), admin: User = Depends(require("admin"))):
    u = s.get(User, uid)
    if not u:
        raise HTTPException(404, "User not found")
    data = body.model_dump(exclude_unset=True)
    if "role" in data and data["role"] not in ROLES:
        raise HTTPException(422, "Unknown role")
    if u.id == admin.id and (data.get("active") is False or data.get("role", "admin") != "admin"):
        raise HTTPException(409, "You can't deactivate or demote your own account.")
    if u.email in DEMO_ADMIN_EMAILS and (data.get("active") is False or data.get("role", "admin") != "admin" or "password" in data):
        raise HTTPException(409, "This is a protected demo account: it can't be deactivated, demoted or have its password changed.")
    if "password" in data:
        u.password_hash = hash_password(data.pop("password"))
    for k, v in data.items():
        setattr(u, k, v)
    bus.audit(s, admin.name, "user.updated", "user", u.id, f"{u.name}: " + ", ".join(data.keys() or ["password"]))
    s.commit()
    return serial.user(u)


# ---------------------------------------------------------------- network (circuit routes)
@router.get("/network/routes", tags=["network"])
def network_routes(s: Session = Depends(get_session), _: User = Depends(current_user)):
    """Every circuit's route for maps, and how many are sandbox-drawn vs imported from GIS."""
    from ..services import network
    return network.routes(s)


@router.post("/admin/network/feeders", tags=["admin"])
def import_feeder_routes(body: dict, s: Session = Depends(get_session), admin: User = Depends(require("admin"))):
    """Import the utility's feeder lines: a GeoJSON FeatureCollection (WGS84) with a feeder ID property per feature."""
    from ..services import network
    try:
        res = network.import_geojson(s, body)
    except network.RouteError as ex:
        raise HTTPException(422, str(ex))
    bus.audit(s, admin.name, "network.imported", "network", "feeders",
              f"GIS feeder routes imported: {res['matched']} matched, {res['unmatched']} not in OMS360")
    s.commit()
    return res


@router.post("/admin/network/feeders/reset", tags=["admin"])
def reset_feeder_routes(s: Session = Depends(get_session), admin: User = Depends(require("admin"))):
    """Back to sandbox-drawn routes (e.g. after a test import)."""
    from ..models import Feeder
    from ..services import network
    for f in s.scalars(select(Feeder)).all():
        f.route, f.route_source = None, None
    n = network.ensure_routes(s)
    bus.audit(s, admin.name, "network.reset", "network", "feeders", f"Feeder routes reset to sandbox drawing ({n})")
    s.commit()
    return {"reset": n}


# ---------------------------------------------------------------- zones
class ZonePatch(BaseModel):
    customers: int | None = Field(None, ge=1)
    water_customers: int | None = Field(None, ge=0)
    vulnerability: float | None = Field(None, ge=0.1, le=1.0)


@router.patch("/admin/zones/{zid}", tags=["admin"])
def update_zone(zid: str, body: ZonePatch, s: Session = Depends(get_session), admin: User = Depends(require("admin"))):
    z = s.get(Zone, zid)
    if not z:
        raise HTTPException(404, "Zone not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(z, k, v)
    bus.audit(s, admin.name, "zone.updated", "zone", z.id, ", ".join(f"{k} → {v}" for k, v in data.items()))
    s.commit()
    return {"ok": True}


# ---------------------------------------------------------------- integrations
@router.get("/admin/integrations", tags=["admin"])
def integrations(s: Session = Depends(get_session), _: User = Depends(require("admin"))):
    key = get_setting(s, "openweather_key")
    return {"connector_mode": get_setting(s, "connector_mode", "sandbox"),
            "openweather": {"configured": bool(key or weather.env_key()), "from_env": not key and bool(weather.env_key()),
                            "masked": f"••••••••{key[-4:]}" if key else ""}}


class IntegrationsIn(BaseModel):
    connector_mode: str | None = None
    openweather_key: str | None = Field(None, max_length=100)


@router.put("/admin/integrations", tags=["admin"])
async def save_integrations(body: IntegrationsIn, s: Session = Depends(get_session), admin: User = Depends(require("admin"))):
    if body.connector_mode is not None:
        if body.connector_mode not in ("off", "sandbox"):
            raise HTTPException(422, "Mode must be off or sandbox")
        set_setting(s, "connector_mode", body.connector_mode)
        bus.audit(s, admin.name, "integration.updated", "setting", "connector_mode", body.connector_mode)
    if body.openweather_key is not None:
        set_setting(s, "openweather_key", body.openweather_key.strip())
        weather.clear_cache()
        bus.audit(s, admin.name, "integration.updated", "setting", "openweather_key", "updated" if body.openweather_key else "removed")
    s.commit()
    result = integrations(s, admin)
    if body.openweather_key is not None:
        result["weather"] = await weather.current(get_setting(s, "openweather_key") or weather.env_key(), force=True)
    return result


# ---------------------------------------------------------------- audit
@router.get("/admin/audit", tags=["admin"])
def audit_log(q: str | None = None, action: str | None = None, limit: int = 200, s: Session = Depends(get_session),
              _: User = Depends(require("admin"))):
    query = select(AuditLog).order_by(AuditLog.id.desc())
    if action:
        query = query.where(AuditLog.action.like(f"{action}%"))
    if q:
        query = query.where(AuditLog.detail.ilike(f"%{q}%") | AuditLog.user_name.ilike(f"%{q}%"))
    return [serial.audit(a) for a in s.scalars(query.limit(min(limit, 1000))).all()]


# ---------------------------------------------------------------- weather
@router.get("/weather", tags=["weather"])
async def current_weather(refresh: bool = False, s: Session = Depends(get_session), _: User = Depends(current_user)):
    key = get_setting(s, "openweather_key") or weather.env_key()
    wx = await weather.current(key, force=refresh)
    return wx | {"radar_available": bool(key) and not wx.get("key_error")}  # radar tiles need a working OpenWeather key


@router.get("/weather/tiles/{layer}/{z}/{x}/{y}.png", tags=["weather"])
async def weather_tile(layer: str, z: int, x: int, y: int, s: Session = Depends(get_session)):
    key = get_setting(s, "openweather_key") or weather.env_key()
    if not key:
        raise HTTPException(404, "No OpenWeather key configured")
    if layer not in weather.TILE_LAYERS:
        raise HTTPException(400, "Unknown layer")
    try:
        png = await weather.tile(key, layer, z, x, y)
    except Exception:
        raise HTTPException(502, "Tile unavailable")
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=600"})
