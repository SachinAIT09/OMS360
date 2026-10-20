"""Asset age and health: transformer fleet by region, circuit and substation, and the asset-register import."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import bus
from ..auth import current_user, require
from ..db import get_session
from ..models import Asset, Feeder, Substation, User
from ..services import assets as svc

router = APIRouter(tags=["assets"])


@router.get("/assets/summary")
def summary(s: Session = Depends(get_session), _: User = Depends(current_user)):
    return svc.summary(s) | {"top_risk": svc.top_risk(s, 10)}


@router.get("/assets/circuits")
def circuits(region: str | None = None, zone: str | None = None, s: Session = Depends(get_session), _: User = Depends(current_user)):
    return svc.circuit_health(s, region, zone)


@router.get("/assets/circuits/{feeder_id}")
def circuit(feeder_id: str, sort: str = "risk", limit: int = 50, offset: int = 0, s: Session = Depends(get_session),
            _: User = Depends(current_user)):
    d = svc.circuit_detail(s, feeder_id.upper(), min(500, max(1, limit)), max(0, offset), sort)
    if not d:
        raise HTTPException(404, f"No transformer records for circuit {feeder_id}")
    return d


@router.get("/assets/substations")
def substations(region: str | None = None, s: Session = Depends(get_session), _: User = Depends(current_user)):
    return svc.substations(s, region)


@router.get("/assets/plan")
def plan(budget: float = 20e6, region: str | None = None, kind: str | None = None, s: Session = Depends(get_session),
         _: User = Depends(current_user)):
    """Replacement plan for a budget: units ranked by customer risk removed per dollar, and the fleet outlook in 5 and 10 years."""
    if kind and kind not in svc.KINDS:
        raise HTTPException(422, f"kind must be one of {', '.join(svc.KINDS)}")
    return svc.replacement_plan(s, max(0.0, min(budget, 2e9)), region, kind)


@router.get("/assets/item/{asset_id}")
def item(asset_id: str, s: Session = Depends(get_session), _: User = Depends(current_user)):
    a = s.get(Asset, asset_id)
    if not a:
        raise HTTPException(404, "Asset not found")
    return svc.serial(a)


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
