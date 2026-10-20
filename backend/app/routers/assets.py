"""Asset age and health: the fleet by region, substation, circuit and unit; history, work orders, the health model and
the asset-register import. Read endpoints need a signed-in user; changes need assets.manage / workorders.manage."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import bus
from ..auth import current_user, require
from ..db import get_session
from ..models import Asset, Feeder, Substation, User, WorkOrder
from ..services import asset_history as hist, asset_model, assets as svc

router = APIRouter(tags=["assets"])


def _kind(kind: str | None) -> str | None:
    if kind and kind not in svc.KINDS:
        raise HTTPException(422, f"kind must be one of {', '.join(svc.KINDS)}")
    return kind


@router.get("/assets/summary")
def summary(region: str | None = None, s: Session = Depends(get_session), _: User = Depends(current_user)):
    return svc.summary(s, region) | {"top_risk": svc.top_risk(s, 10, region), "model_status": asset_model.methodology()["status"]}


@router.get("/assets/circuits")
def circuits(region: str | None = None, zone: str | None = None, substation: str | None = None, s: Session = Depends(get_session),
             _: User = Depends(current_user)):
    return svc.circuit_health(s, region, zone, substation)


@router.get("/assets/circuits/{feeder_id}")
def circuit(feeder_id: str, sort: str = "risk", limit: int = 50, offset: int = 0, kind: str = svc.DIST, s: Session = Depends(get_session),
            _: User = Depends(current_user)):
    d = svc.circuit_detail(s, feeder_id.upper(), min(500, max(1, limit)), max(0, offset), sort, _kind(kind) or svc.DIST)
    if not d:
        raise HTTPException(404, f"No asset records for circuit {feeder_id}")
    return d


@router.get("/assets/circuits/{feeder_id}/markers")
def circuit_markers(feeder_id: str, s: Session = Depends(get_session), _: User = Depends(current_user)):
    if not s.get(Feeder, feeder_id.upper()):
        raise HTTPException(404, f"Circuit {feeder_id} not found")
    return svc.circuit_markers(s, feeder_id.upper())


@router.get("/assets/substations")
def substations(region: str | None = None, s: Session = Depends(get_session), _: User = Depends(current_user)):
    """Substation power transformers (one row per unit)."""
    return svc.substations(s, region)


@router.get("/network/substations")
def substation_rollup(region: str | None = None, s: Session = Depends(get_session), _: User = Depends(current_user)):
    """One row per substation: circuits, customers, worst unit and fleet health below it."""
    return svc.substation_rollup(s, region)


@router.get("/network/substations/{sub_id}")
def substation(sub_id: str, s: Session = Depends(get_session), _: User = Depends(current_user)):
    sub = s.get(Substation, sub_id.upper())
    if not sub:
        raise HTTPException(404, "Substation not found")
    row = next((r for r in svc.substation_rollup(s) if r["id"] == sub.id), None)
    units = s.scalars(select(Asset).where(Asset.substation_id == sub.id, Asset.kind.in_((svc.POWER, svc.BREAKER))).order_by(Asset.kind.desc(), Asset.id)).all()
    return {**(row or {"id": sub.id, "name": sub.name}), "circuits_detail": svc.circuit_health(s, substation=sub.id),
            "units": [svc.serial(a) for a in units]}


@router.get("/network/geo")
def geo(s: Session = Depends(get_session)):
    """Map outlines (public): the state boundary, and each operating region's approximate service area — the convex hull of
    its circuits and substations, padded ~2 km. Region areas are drawn from the (sandbox) network, not a filed territory map."""
    import json
    from pathlib import Path
    from ..data import TERRITORY
    from ..models import Region, Zone
    f = Path(__file__).resolve().parent.parent / "territories" / "geo" / f"{TERRITORY}.json"
    state = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    zones = {z.id: z.region_id for z in s.scalars(select(Zone)).all()}
    pts: dict[str, list[tuple[float, float]]] = {}
    for fd in s.scalars(select(Feeder)).all():
        for line in fd.route or []:
            pts.setdefault(zones.get(fd.zone_id), []).extend((p[0], p[1]) for p in line)
    names = {r.id: r.name for r in s.scalars(select(Region)).all()}
    return {"state": state, "regions": [{"id": rid, "name": names.get(rid, rid), "hull": _hull(p, 0.02)} for rid, p in pts.items() if rid and len(p) >= 3],
            "note": "Region areas are approximate: the outline of each region's circuits."}


def _hull(points: list[tuple[float, float]], pad: float) -> list[list[float]]:
    """Convex hull (monotone chain) of (lat, lng) points, pushed out by `pad` degrees from its centroid."""
    import math
    p = sorted(set(points))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for q in p:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    for q in reversed(p):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    h = lower[:-1] + upper[:-1]
    cy, cx = sum(q[0] for q in h) / len(h), sum(q[1] for q in h) / len(h)
    out = []
    for la, ln in h:
        d = math.hypot(la - cy, ln - cx) or 1
        out.append([round(la + (la - cy) / d * pad, 4), round(ln + (ln - cx) / d * pad, 4)])
    return out


@router.get("/assets/plan")
def plan(budget: float = 20e6, region: str | None = None, kind: str | None = None, s: Session = Depends(get_session),
         _: User = Depends(current_user)):
    """Replacement plan for a budget: units ranked by customer risk removed per dollar, and the fleet outlook in 5 and 10 years."""
    return svc.replacement_plan(s, max(0.0, min(budget, 2e9)), region, _kind(kind))


@router.get("/assets/top")
def top(n: int = 25, region: str | None = None, kind: str | None = None, s: Session = Depends(get_session), _: User = Depends(current_user)):
    return svc.top_risk(s, min(200, max(1, n)), region, _kind(kind))


@router.get("/assets/search")
def search(q: str, s: Session = Depends(get_session), _: User = Depends(current_user)):
    return svc.search(s, q) if len(q.strip()) >= 2 else []


@router.get("/assets/item/{asset_id}")
def item(asset_id: str, s: Session = Depends(get_session), _: User = Depends(current_user)):
    d = hist.asset_detail(s, asset_id.upper())
    if not d:
        raise HTTPException(404, "Asset not found")
    return d


# ---------------------------------------------------------------- work orders
class WorkOrderIn(BaseModel):
    kind: str = Field(pattern="^(inspect|test|repair|replace|maintain)$")
    title: str = Field(min_length=3, max_length=160)
    reason: str = ""
    priority: str = Field("Medium", pattern="^(Critical|High|Medium|Low)$")
    due_days: int | None = Field(None, ge=1, le=730)
    event_id: int | None = None


@router.post("/assets/item/{asset_id}/work-orders", status_code=201)
def create_wo(asset_id: str, body: WorkOrderIn, s: Session = Depends(get_session), user: User = Depends(require("workorders.manage"))):
    a = s.get(Asset, asset_id.upper())
    if not a:
        raise HTTPException(404, "Asset not found")
    w = hist.create_work_order(s, a, body.kind, body.title, body.reason, body.priority, user.name, body.due_days, body.event_id)
    bus.audit(s, user.name, "workorder.created", "work_order", w.id, f"{w.title} — {a.id}", body.event_id)
    s.commit()
    bus.publish("assets")
    return hist.wo_serial(w)


class WorkOrderPatch(BaseModel):
    status: str = Field(pattern="^(open|scheduled|done|cancelled)$")


@router.patch("/work-orders/{wo_id}")
def update_wo(wo_id: int, body: WorkOrderPatch, s: Session = Depends(get_session), user: User = Depends(require("workorders.manage"))):
    w = s.get(WorkOrder, wo_id)
    if not w:
        raise HTTPException(404, "Work order not found")
    prev, w.status = w.status, body.status
    bus.audit(s, user.name, "workorder.status", "work_order", w.id, f"{w.title}: {prev} → {body.status}", w.event_id)
    s.commit()
    bus.publish("assets")
    return hist.wo_serial(w)


@router.get("/work-orders")
def list_wo(status: str | None = None, region: str | None = None, s: Session = Depends(get_session), _: User = Depends(current_user)):
    return hist.work_orders(s, status, region)


# ---------------------------------------------------------------- health model
@router.get("/assets/model")
def model(_: User = Depends(current_user)):
    return asset_model.methodology()


class WeightsIn(BaseModel):
    weights: dict[str, float]


@router.put("/admin/assets/model")
def set_model(body: WeightsIn, s: Session = Depends(get_session), user: User = Depends(require("assets.manage"))):
    try:
        w = svc.apply_weights(s, body.weights)
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    bus.audit(s, user.name, "assets.model", "asset", "", "Asset health weights changed: " + ", ".join(f"{k}={v:g}" for k, v in w.items()))
    s.commit()
    bus.publish("assets")
    return asset_model.methodology()


# ---------------------------------------------------------------- import
class ImportIn(BaseModel):
    csv: str = Field(min_length=10)
    replace: bool = False  # clear the sandbox register first


@router.post("/admin/assets/import")
def import_assets(body: ImportIn, s: Session = Depends(get_session), user: User = Depends(require("assets.manage"))):
    try:
        res = svc.import_csv(s, body.csv, body.replace)
    except svc.AssetImportError as ex:
        s.rollback()
        raise HTTPException(422, str(ex))
    bus.audit(s, user.name, "assets.imported", "asset", "", f"Asset register import: {res['added']} added, {res['updated']} updated"
              + (" (replaced sandbox register)" if body.replace else ""))
    s.commit()
    bus.publish("assets")
    return res


@router.get("/admin/assets/sample")
def sample(s: Session = Depends(get_session), _: User = Depends(require("assets.manage"))):
    f = s.scalars(select(Feeder).order_by(Feeder.id)).first()
    sub = s.scalars(select(Substation).order_by(Substation.id)).first()
    return {"csv": svc.SAMPLE_CSV.format(feeder=f.id if f else "FDR-XXX-01", sub=sub.id if sub else "SUB-XXX-1"), "fields": list(svc.FIELDS),
            "density": svc.density()}
