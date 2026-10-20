"""Storm events: lifecycle, predictions, NHC import, recommendations, overview."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import bus, serial
from ..auth import current_user, require
from ..db import get_session
from ..models import AuditLog, ForecastRun, Message, Outage, PredictionRun, Recommendation, StormEvent, Task, User, Zone, utcnow
from ..services import forecast as fc_svc, nhc, nws, ops, recommendations as recs
from ..data import NEW_EVENT, WEATHER_POINT
from ..territories.common import EF_WIDTH_M, EF_WIND, path_track
from ..services.events import EVENT_KINDS, RAIN, TORNADO, LifecycleError, change_status
from ..services.prediction import predict

router = APIRouter(tags=["events"])


def get_event(s: Session, event_id: int) -> StormEvent:
    e = s.get(StormEvent, event_id)
    if not e:
        raise HTTPException(404, "Storm event not found")
    return e


@router.get("/events")
def list_events(s: Session = Depends(get_session), _: User = Depends(current_user)):
    rows = []
    for e in s.scalars(select(StormEvent).order_by(StormEvent.created_at.desc())).all():
        pr = recs.latest_prediction(s, e.id)
        tickets = s.scalar(select(func.count()).select_from(Outage).where(Outage.event_id == e.id))
        affected = s.scalar(select(func.sum(Outage.customers)).where(Outage.event_id == e.id)) or 0
        rows.append({**serial.event(e), "track": None, "predicted": pr.result["pred_total"] if pr else None,
                     "tickets": tickets, "customers_affected": affected})
    return rows


@router.get("/events/current")
def current_event(s: Session = Depends(get_session), _: User = Depends(current_user)):
    e = s.scalars(select(StormEvent).where(StormEvent.status != "closed").order_by(StormEvent.created_at.desc())).first()
    return serial.event(e) if e else None


class EventIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    kind: str = NEW_EVENT["kind"]  # one of EVENT_KINDS
    category: int = Field(1, ge=0, le=5)  # Saffir-Simpson category; EF rating (0–5) for tornadoes
    max_wind_mph: int = Field(90, ge=20, le=220)
    pressure_mb: int = Field(980, ge=850, le=1030)
    lat: float = NEW_EVENT["lat"]
    lng: float = NEW_EVENT["lng"]
    heading_deg: float = 30
    speed_mph: float = 12
    landfall_at: datetime | None = None  # rain events: rain onset
    notes: str = ""
    rain_total_in: float | None = Field(None, ge=0.5, le=40)
    rain_rate_in_hr: float | None = Field(None, ge=0.1, le=8)
    duration_h: float | None = Field(None, ge=1, le=240)
    soil_saturation: float | None = Field(None, ge=0, le=1)
    # Tornadoes: a damage path from (lat, lng) along heading_deg, at speed_mph forward speed
    path_length_mi: float | None = Field(None, ge=0.5, le=200)
    path_width_m: int | None = Field(None, ge=30, le=4000)


@router.post("/events", status_code=201)
def create_event(body: EventIn, s: Session = Depends(get_session), user: User = Depends(require("events.manage"))):
    if body.kind not in EVENT_KINDS:
        raise HTTPException(422, f"Event type must be one of: {', '.join(EVENT_KINDS)}")
    now = utcnow()
    if body.kind == RAIN:
        # No track or category: a rain event is described by rainfall over the territory.
        e = StormEvent(name=body.name, kind=body.kind, category=1, max_wind_mph=min(body.max_wind_mph, 39), pressure_mb=body.pressure_mb,
                       lat=WEATHER_POINT["lat"], lng=WEATHER_POINT["lon"], movement="", landfall_at=body.landfall_at, notes=body.notes, created_by=user.id, track=[],
                       rain_total_in=body.rain_total_in or 4.0, rain_rate_in_hr=body.rain_rate_in_hr or 1.0,
                       duration_h=body.duration_h or 12, soil_saturation=0.5 if body.soil_saturation is None else body.soil_saturation)
    elif body.kind == TORNADO:
        e = StormEvent(name=body.name, kind=body.kind, category=body.category, max_wind_mph=body.max_wind_mph, pressure_mb=body.pressure_mb,
                       lat=body.lat, lng=body.lng, movement=f"{nhc._compass(body.heading_deg)} at {round(body.speed_mph)} mph",
                       landfall_at=body.landfall_at, notes=body.notes, created_by=user.id,
                       track=tornado_track(body.lat, body.lng, body.heading_deg, body.path_length_mi or 15, body.category,
                                           body.path_width_m, body.speed_mph, body.landfall_at or now, now))
    else:
        e = StormEvent(name=body.name, kind=body.kind, category=max(1, body.category), max_wind_mph=body.max_wind_mph, pressure_mb=body.pressure_mb,
                       lat=body.lat, lng=body.lng, movement=f"{nhc._compass(body.heading_deg)} at {round(body.speed_mph)} mph",
                       landfall_at=body.landfall_at, notes=body.notes, created_by=user.id,
                       track=nhc.project_track(body.lat, body.lng, body.heading_deg, body.speed_mph, now))
    s.add(e)
    s.flush()
    bus.audit(s, user.name, "event.created", "storm_event", e.id, f"{e.name} created (Monitoring)", e.id)
    s.commit()
    bus.publish("events")
    return serial.event(e)


def tornado_track(lat: float, lng: float, heading_deg: float, length_mi: float, ef: int, width_m: int | None, speed_mph: float,
                  touchdown: datetime, now: datetime) -> list[dict]:
    """A straight damage path from the touchdown point, split into ~2-mile steps so circuits are matched along its length."""
    import math
    n = max(1, round(length_mi / 2))
    pts = []
    for i in range(n + 1):
        d = length_mi * i / n
        pts.append([round(lat + d * math.cos(math.radians(heading_deg)) / 69, 4),
                    round(lng + d * math.sin(math.radians(heading_deg)) / (69 * math.cos(math.radians(lat))), 4)])
    paths = [{"ef": ef, "width_m": width_m or EF_WIDTH_M[ef], "start_h": 0, "mph": max(5.0, speed_mph), "points": pts}]
    return path_track(paths, touchdown, now)


class EventPatch(BaseModel):
    category: int | None = Field(None, ge=1, le=5)
    max_wind_mph: int | None = None
    pressure_mb: int | None = None
    landfall_at: datetime | None = None
    notes: str | None = None
    rain_total_in: float | None = Field(None, ge=0.5, le=40)
    rain_rate_in_hr: float | None = Field(None, ge=0.1, le=8)
    duration_h: float | None = Field(None, ge=1, le=240)
    soil_saturation: float | None = Field(None, ge=0, le=1)


@router.patch("/events/{event_id}")
def update_event(event_id: int, body: EventPatch, s: Session = Depends(get_session), user: User = Depends(require("events.manage"))):
    e = get_event(s, event_id)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(e, k, v)
    bus.audit(s, user.name, "event.updated", "storm_event", e.id, ", ".join(f"{k} → {v}" for k, v in changes.items()), e.id)
    s.commit()
    bus.publish("events")
    return serial.event(e)


class StatusIn(BaseModel):
    status: str


@router.post("/events/{event_id}/status")
def set_status(event_id: int, body: StatusIn, s: Session = Depends(get_session), user: User = Depends(require("events.manage"))):
    e = get_event(s, event_id)
    try:
        change_status(s, e, body.status, user.name)
    except LifecycleError as ex:
        raise HTTPException(409, str(ex))
    s.commit()
    return serial.event(e)


@router.get("/events/{event_id}")
def event_detail(event_id: int, s: Session = Depends(get_session), _: User = Depends(current_user)):
    e = get_event(s, event_id)
    pr = recs.latest_prediction(s, e.id)
    return {**serial.event(e), "prediction": _run(pr) if pr else None, "stats": ops.event_stats(s, e)}


def _run(pr: PredictionRun) -> dict:
    return {"id": pr.id, "category": pr.category, "created_at": pr.created_at, "result": pr.result}


@router.get("/events/{event_id}/overview")
def overview(event_id: int, s: Session = Depends(get_session), _: User = Depends(current_user)):
    e = get_event(s, event_id)
    pr = recs.latest_prediction(s, e.id)
    tasks = s.scalars(select(Task).where(Task.event_id == e.id).order_by(Task.status, Task.id.desc())).all()
    activity = s.scalars(select(AuditLog).where(AuditLog.event_id == e.id).order_by(AuditLog.id.desc()).limit(25)).all()
    pending_msgs = s.scalar(select(func.count(Message.id)).where(Message.event_id == e.id, Message.status == "pending"))
    return {"event": serial.event(e), "prediction": _run(pr) if pr else None, "stats": ops.event_stats(s, e),
            "curve": ops.restoration_curve(s, e) if e.status in ("active", "restoring", "closed") else None,
            "tasks": [serial.task(t) for t in tasks], "activity": [serial.audit(a) for a in activity], "pending_messages": pending_msgs}


class PredictIn(BaseModel):
    category: int | None = Field(None, ge=1, le=5)
    rain_in: float | None = Field(None, ge=0.5, le=40)  # rain events: rainfall scenario
    use_forecast: bool = True  # with no category / rain_in, use the latest imported forecast per zone
    save: bool = True


@router.post("/events/{event_id}/predictions")
def run_prediction(event_id: int, body: PredictIn, s: Session = Depends(get_session), user: User = Depends(require("predictions.run"))):
    e = get_event(s, event_id)
    res = predict(s, e, body.category, body.rain_in, body.use_forecast)
    if not body.save:
        return {"id": None, "category": res["category"], "created_at": utcnow(), "result": res}
    pr = PredictionRun(event_id=e.id, category=res["category"], result=res, created_by=user.id)
    s.add(pr)
    bus.audit(s, user.name, "prediction.run", "storm_event", e.id, f"{res['scenario']} prediction: {res['pred_total']:,} customers", e.id)
    s.commit()
    bus.publish("predictions")
    return _run(pr)


@router.get("/events/{event_id}/predictions")
def predictions(event_id: int, s: Session = Depends(get_session), _: User = Depends(current_user)):
    runs = s.scalars(select(PredictionRun).where(PredictionRun.event_id == event_id).order_by(PredictionRun.id.desc())).all()
    users = {u.id: u.name for u in s.scalars(select(User)).all()}
    return [{"id": r.id, "category": r.category, "created_at": r.created_at, "created_by": users.get(r.created_by, "System"),
             "scenario": r.result.get("scenario", f"Cat {r.category}"), "pred_total": r.result["pred_total"], "required_line": r.result["required"]["line"]} for r in runs]


@router.get("/events/{event_id}/timeline")
def timeline(event_id: int, s: Session = Depends(get_session), _: User = Depends(current_user)):
    rows = s.scalars(select(AuditLog).where(AuditLog.event_id == event_id).order_by(AuditLog.id.desc()).limit(300)).all()
    return [serial.audit(a) for a in rows]


# ---------------------------------------------------------------- recommendations
@router.get("/events/{event_id}/recommendations")
def list_recommendations(event_id: int, s: Session = Depends(get_session), _: User = Depends(current_user)):
    return [serial.recommendation(r) for r in recs.refresh(s, get_event(s, event_id))]


def _decide(rec_id: int, s: Session, user: User, approve: bool):
    r = s.get(Recommendation, rec_id)
    if not r:
        raise HTTPException(404, "Recommendation not found")
    if r.status != "open":
        raise HTTPException(409, f"Already {r.status} by {r.decided_by}.")
    e = get_event(s, r.event_id)
    r.status, r.decided_by, r.decided_at = ("approved" if approve else "dismissed"), user.name, utcnow()
    if approve:
        try:
            r.outcome = recs.execute(s, e, r, user.name)
        except (LifecycleError, ops.OpsError) as ex:
            raise HTTPException(409, str(ex))
    bus.audit(s, user.name, f"recommendation.{r.status}", "recommendation", r.id, r.title + (f" — {r.outcome}" if r.outcome else ""), e.id)
    s.commit()
    bus.publish("recommendations")
    return serial.recommendation(r)


@router.post("/recommendations/{rec_id}/approve")
def approve(rec_id: int, s: Session = Depends(get_session), user: User = Depends(require("recommendations.decide"))):
    return _decide(rec_id, s, user, True)


@router.post("/recommendations/{rec_id}/dismiss")
def dismiss(rec_id: int, s: Session = Depends(get_session), user: User = Depends(require("recommendations.decide"))):
    return _decide(rec_id, s, user, False)


# ---------------------------------------------------------------- NHC
@router.get("/nhc/storms")
async def nhc_storms(_: User = Depends(current_user)):
    try:
        return {"storms": nhc.parse(await nhc.fetch()), "error": None, "source": nhc.FEED}
    except Exception as e:
        return {"storms": [], "error": f"NHC feed unavailable: {e}", "source": nhc.FEED}


class ImportIn(BaseModel):
    nhc_id: str
    landfall_at: datetime | None = None


@router.post("/events/import-nhc", status_code=201)
async def import_nhc(body: ImportIn, s: Session = Depends(get_session), user: User = Depends(require("events.manage"))):
    storms = {st["nhc_id"]: st for st in nhc.parse(await nhc.fetch())}
    st = storms.get(body.nhc_id)
    if not st:
        raise HTTPException(404, "That storm is no longer in the NHC active storms feed.")
    if s.scalars(select(StormEvent).where(StormEvent.nhc_id == body.nhc_id, StormEvent.status != "closed")).first():
        raise HTTPException(409, f"{st['name']} is already being tracked.")
    start = datetime.fromisoformat(st["updated_at"])
    e = StormEvent(name=f"{st['kind']} {st['name']}", kind=st["kind"], source="nhc", nhc_id=st["nhc_id"], category=max(1, st["category"]),
                   max_wind_mph=st["wind_mph"], pressure_mb=st["pressure_mb"] or 1000, lat=st["lat"], lng=st["lng"], movement=st["movement"],
                   landfall_at=body.landfall_at, created_by=user.id,
                   track=nhc.project_track(st["lat"], st["lng"], st["heading_deg"], st["speed_mph"], start),
                   notes=f"Imported from NHC advisory ({st['updated_at']}). {st['advisory_url']}")
    s.add(e)
    s.flush()
    bus.audit(s, user.name, "event.imported", "storm_event", e.id, f"{e.name} imported from NHC ({st['nhc_id']})", e.id)
    s.commit()
    bus.publish("events")
    return serial.event(e)


@router.get("/events/{event_id}/impact")
def impact(event_id: int, s: Session = Depends(get_session), _: User = Depends(current_user)):
    """Network impact of the storm in one place: regions, substations and circuits on the predicted paths, assets to inspect,
    damage confirmed in the field so far, critical facilities."""
    from ..services.asset_history import storm_impact
    return storm_impact(s, get_event(s, event_id))


# ---------------------------------------------------------------- NWS (tornado warnings) and surveyed damage paths
@router.get("/nws/alerts")
async def nws_alerts(_: User = Depends(current_user)):
    try:
        return {"alerts": nws.parse(await nws.fetch()), "error": None, "source": f"{nws.FEED}?area={nws.STATE_CODE}"}
    except Exception as e:
        return {"alerts": [], "error": f"NWS alerts feed unavailable: {e}", "source": nws.FEED}


class NwsImportIn(BaseModel):
    alert_id: str | None = None
    sample: bool = False  # sandbox: import the built-in sample warning


@router.post("/events/import-nws", status_code=201)
async def import_nws(body: NwsImportIn, s: Session = Depends(get_session), user: User = Depends(require("events.manage"))):
    if body.sample:
        a = nws.parse(nws.sample_feed())[0]
        return _create_from_warning(s, a, user)
    alerts = {a["id"]: a for a in nws.parse(await nws.fetch())}
    a = alerts.get(body.alert_id or "")
    if not a or not a["importable"]:
        raise HTTPException(404, "That tornado warning is no longer active in the NWS feed.")
    return _create_from_warning(s, a, user)


def _create_from_warning(s: Session, a: dict, user: User) -> dict:
    key = a["id"][-20:]
    if s.scalars(select(StormEvent).where(StormEvent.nhc_id == key, StormEvent.status != "closed")).first():
        raise HTTPException(409, "That warning is already being tracked.")
    now = utcnow()
    path = nws.warning_path(a, now)
    mv = a.get("motion") or {}
    counties = [c.strip() for c in a["area"].split(";") if c.strip()]
    area = (", ".join(counties[:2]) + (f" +{len(counties) - 2}" if len(counties) > 2 else "")) or "storm"
    e = StormEvent(name=f"Tornado Warning — {area}"[:80], kind=TORNADO, source="nws", nhc_id=key, category=path["ef"],
                   max_wind_mph=EF_WIND[path["ef"]] + 10, pressure_mb=995, lat=path["points"][0][0], lng=path["points"][0][1],
                   movement=f"{nhc._compass(mv['heading_deg'])} at {mv['speed_mph']} mph" if mv else "", landfall_at=path["touchdown"],
                   created_by=user.id, track=path_track([path], path["touchdown"], now),
                   notes=f"Imported from NWS: {a['headline']}. Detection: {a['detection'] or 'n/a'}; damage threat: {a['damage_threat'] or 'base'}. "
                         f"Planning path {path['length_mi']} mi along the storm motion, rated EF{path['ef']} from the warning tags; "
                         "replace it with the damage survey once available.")
    s.add(e)
    s.flush()
    bus.audit(s, user.name, "event.imported", "storm_event", e.id, f"{e.name} imported from NWS ({a['event']})", e.id)
    res = predict(s, e)
    s.add(PredictionRun(event_id=e.id, category=res["category"], result=res, created_by=user.id))
    s.commit()
    bus.publish("events")
    return serial.event(e)


class PathIn(BaseModel):
    ef: int = Field(ge=0, le=5)
    width_m: int | None = Field(None, ge=30, le=4000)
    points: list[list[float]] = Field(min_length=2)
    start_h: float = 0
    mph: float = Field(30, gt=0, le=90)


class PathsIn(BaseModel):
    paths: list[PathIn] | None = None
    csv: str | None = None  # path,ef,width_m,lat,lng — one row per point
    surveyed: bool = True   # NWS damage survey (observed) vs a revised planning path


def parse_path_csv(text: str) -> list[dict]:
    import csv as csvlib
    import io
    rows = list(csvlib.DictReader(io.StringIO(text.strip())))
    if not rows or not {"ef", "lat", "lng"} <= {k.strip().lower() for k in rows[0]}:
        raise HTTPException(422, "CSV needs a header: path,ef,width_m,lat,lng (one row per point along each path)")
    paths: dict[str, dict] = {}
    for i, raw in enumerate(rows, 2):
        r = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        try:
            p = paths.setdefault(r.get("path") or "1", {"ef": int(r["ef"]), "width_m": int(float(r["width_m"])) if r.get("width_m") else None, "points": []})
            p["points"].append([float(r["lat"]), float(r["lng"])])
        except (ValueError, KeyError):
            raise HTTPException(422, f"Row {i}: ef, lat and lng must be numbers.")
    return list(paths.values())


@router.put("/events/{event_id}/paths")
def replace_paths(event_id: int, body: PathsIn, s: Session = Depends(get_session), user: User = Depends(require("events.manage"))):
    """Replace a tornado event's damage paths (e.g. with the NWS damage survey) and re-run the prediction on them."""
    e = get_event(s, event_id)
    if e.kind != TORNADO:
        raise HTTPException(409, "Damage paths apply to tornado events only.")
    raw = parse_path_csv(body.csv) if body.csv else [p.model_dump() for p in body.paths or []]
    if not raw:
        raise HTTPException(422, "Give at least one path with two or more points.")
    paths = []
    for i, p in enumerate(raw, 1):
        p = PathIn(**p).model_dump()  # validates CSV rows too
        if any(not (-90 <= la <= 90 and -180 <= ln <= 180) for la, ln in p["points"]):
            raise HTTPException(422, f"Path {i}: points must be [lat, lng].")
        paths.append(p | {"width_m": p["width_m"] or EF_WIDTH_M[p["ef"]]})
    now = utcnow()
    track = path_track(paths, e.landfall_at or now, now)
    if body.surveyed:
        for pt in track:
            pt["observed"] = True
    e.track, e.category = track, max(p["ef"] for p in paths)
    e.lat, e.lng = paths[0]["points"][0]
    e.max_wind_mph = EF_WIND[e.category] + 10
    res = predict(s, e)
    s.add(PredictionRun(event_id=e.id, category=res["category"], result=res, created_by=user.id))
    label = "NWS damage survey" if body.surveyed else "revised planning paths"
    bus.audit(s, user.name, "event.paths", "storm_event", e.id, f"{e.name}: {len(paths)} damage path(s) from the {label}; prediction re-run: "
              f"{res['pred_total']:,} customers, {res['circuits_in_path']} circuits in the paths", e.id)
    s.commit()
    bus.publish("events")
    return {**serial.event(e), "prediction": {"pred_total": res["pred_total"], "circuits_in_path": res["circuits_in_path"]}}


# ---------------------------------------------------------------- tasks
class TaskIn(BaseModel):
    event_id: int | None = None
    title: str = Field(min_length=3, max_length=200)
    owner_role: str = "ops_manager"
    due_at: datetime | None = None


@router.get("/tasks")
def list_tasks(event_id: int | None = None, s: Session = Depends(get_session), _: User = Depends(current_user)):
    q = select(Task).order_by(Task.status, Task.id.desc())
    if event_id:
        q = q.where(Task.event_id == event_id)
    return [serial.task(t) for t in s.scalars(q).all()]


@router.post("/tasks", status_code=201)
def create_task(body: TaskIn, s: Session = Depends(get_session), user: User = Depends(require("tasks.manage"))):
    t = Task(**(body.model_dump() | {"due_at": body.due_at or utcnow() + timedelta(hours=12)}))
    s.add(t)
    s.flush()
    bus.audit(s, user.name, "task.created", "task", t.id, t.title, t.event_id)
    s.commit()
    bus.publish("tasks")
    return serial.task(t)


@router.post("/tasks/{task_id}/done")
def complete_task(task_id: int, s: Session = Depends(get_session), user: User = Depends(require("tasks.manage"))):
    t = s.get(Task, task_id)
    if not t:
        raise HTTPException(404, "Task not found")
    t.status, t.done_at = "done", utcnow()
    bus.audit(s, user.name, "task.done", "task", t.id, t.title, t.event_id)
    s.commit()
    bus.publish("tasks")
    return serial.task(t)


# ---------------------------------------------------------------- outside forecasts (parent-company storm model)
class ForecastIn(BaseModel):
    source: str = Field(fc_svc.PARENT_SOURCE, min_length=2, max_length=80)
    issued_at: datetime | None = None
    zones: list[dict] | None = None  # [{zone, gust_mph, rain_in, surge_ft, arrival_at}]
    csv: str | None = Field(None, max_length=200_000)
    mock: bool = False  # sandbox: generate the parent model's output from the event


@router.get("/events/{event_id}/forecasts")
def forecasts(event_id: int, s: Session = Depends(get_session), _: User = Depends(current_user)):
    get_event(s, event_id)
    names = {z.id: z.short for z in s.scalars(select(Zone)).all()}
    rows = s.scalars(select(ForecastRun).where(ForecastRun.event_id == event_id).order_by(ForecastRun.id.desc())).all()
    return {"latest": fc_svc.serial(rows[0], names) if rows else None,
            "history": [{"id": r.id, "source": r.source, "issued_at": r.issued_at, "created_by": r.created_by} for r in rows],
            "sample_csv": fc_svc.SAMPLE_CSV}


@router.post("/events/{event_id}/forecasts", status_code=201)
def import_forecast(event_id: int, body: ForecastIn, s: Session = Depends(get_session), user: User = Depends(require("predictions.run"))):
    """Import a forecast (JSON rows, CSV text or the sandbox mock feed) and re-run the prediction on it."""
    e = get_event(s, event_id)
    try:
        if body.mock:
            zones = fc_svc.mock_parent_forecast(s, e, seed=int(utcnow().timestamp()) // 3600)
        elif body.csv:
            zones = fc_svc.normalize(s, fc_svc.parse_csv(body.csv))
        elif body.zones:
            zones = fc_svc.normalize(s, body.zones)
        else:
            raise fc_svc.ForecastError("Send forecast rows, CSV text, or mock: true.")
    except fc_svc.ForecastError as ex:
        raise HTTPException(422, str(ex))
    fc = fc_svc.save(s, e, zones, body.source, user.name, body.issued_at)
    res = predict(s, e)
    s.add(PredictionRun(event_id=e.id, category=res["category"], result=res, created_by=user.id))
    bus.audit(s, user.name, "forecast.imported", "storm_event", e.id,
              f"{fc.source} forecast for {len(zones)} zones; prediction re-run: {res['pred_total']:,} customers", e.id)
    s.commit()
    bus.publish("predictions")
    names = {z.id: z.short for z in s.scalars(select(Zone)).all()}
    return fc_svc.serial(fc, names)
