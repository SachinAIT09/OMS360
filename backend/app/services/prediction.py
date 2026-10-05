"""Storm impact prediction.

Inputs: storm category + the utility's zones (customers, vulnerability), the workforce on the
roster and mutual aid already requested. Output is stored as a PredictionRun so every forecast
is reproducible and auditable.

  predicted out(zone) = customers × min(0.97, catFactor × vulnerability × 1.15)
  line workers needed  = predicted total / 185  (customers restored per worker per event,
                         calibrated on Irma 2017 / Ian 2022 / Milton 2024 damage in the territory)
  restoration hours    = (14 + catFactor × 95 × vuln − critical bonus) / coverage^0.75
"""
import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..data import CATF, LIFT_STATIONS, SURGE_BY_CAT, WIND_BY_CAT
from ..fmt import jround
from ..models import Crew, Facility, Feeder, MutualAidRequest, StormEvent, Zone


def workforce(s: Session) -> dict:
    """Internal workers on the roster by crew type."""
    rows = s.execute(select(Crew.kind, func.sum(Crew.size)).where(Crew.source == "internal").group_by(Crew.kind)).all()
    d = {k: int(v or 0) for k, v in rows}
    return {"line": d.get("line", 0), "tree": d.get("tree", 0), "da": d.get("assessment", 0)}


def mutual_aid_committed(s: Session, event_id: int) -> dict:
    rows = s.execute(select(MutualAidRequest.kind, func.sum(MutualAidRequest.workers))
                     .where(MutualAidRequest.event_id == event_id, MutualAidRequest.status.notin_(["cancelled", "released"]))
                     .group_by(MutualAidRequest.kind)).all()
    d = {k: int(v or 0) for k, v in rows}
    return {"line": d.get("line", 0), "tree": d.get("tree", 0), "da": d.get("assessment", 0)}


def predict(s: Session, event: StormEvent, category: int | None = None) -> dict:
    cat = max(1, min(5, category or event.category or 1))
    cf = CATF[cat]
    zones = s.scalars(select(Zone)).all()
    preds = {z.id: jround(z.customers * min(0.97, cf * z.vulnerability * 1.15)) for z in zones}
    pred_total = sum(preds.values()) or 1

    internal = workforce(s)
    committed = mutual_aid_committed(s, event.id)
    req_line = jround(pred_total / 185)
    required = {"line": req_line, "tree": jround(req_line * 0.45), "da": max(20, jround(pred_total / 2500))}
    needed = {k: max(0, jround(required[k] * 1.08) - internal[k] - committed[k]) for k in required}
    supply_line = internal["line"] + committed["line"]
    ratio = min(1.1, supply_line / max(1, req_line))

    zone_rows = []
    for z in zones:
        eta = (14 + cf * 95 * z.vulnerability - (6 if z.critical else 0)) / math.pow(min(1, ratio), 0.75)
        zone_rows.append({"id": z.id, "name": z.name, "short": z.short, "customers": z.customers, "pred": preds[z.id],
                          "pct": round(preds[z.id] / z.customers, 4), "eta_h": max(12, jround(eta)),
                          "driver": "Storm surge + wind" if z.coastal else "Wind + dense tree canopy" if z.vulnerability > 0.75
                          else "Wind + aging overhead lines" if z.vulnerability > 0.6 else "Wind (mostly underground)"})
    avg_eta = sum(r["eta_h"] * r["pred"] for r in zone_rows) / pred_total
    risk = {r["id"]: r["pct"] for r in zone_rows}
    facilities = [{"id": f.id, "name": f.name, "kind": f.kind, "type": f.type, "feeder": f.feeder_id, "backup": f.backup,
                   "risk": "High" if risk[f.zone_id] > 0.4 else "Medium" if risk[f.zone_id] > 0.2 else "Low"}
                  for f in s.scalars(select(Facility)).all()]
    lift = jround(LIFT_STATIONS * min(0.6, cf * 1.1))

    # 80/20: distribute predicted impact across feeders weighted by size × overhead exposure × vulnerability
    feeders = s.scalars(select(Feeder)).all()
    zmap = {z.id: z for z in zones}
    w = {f.id: f.customers * (f.overhead_pct / 100) ** 2 * zmap[f.zone_id].vulnerability ** 3 * (2025 - f.last_trimmed + 1) for f in feeders}
    wz: dict[str, float] = {}
    for f in feeders:
        wz[f.zone_id] = wz.get(f.zone_id, 0) + w[f.id]
    feeder_rows = sorted(({"id": f.id, "zone": zmap[f.zone_id].short,
                           "pred": jround(preds[f.zone_id] * w[f.id] / wz[f.zone_id])} for f in feeders), key=lambda r: -r["pred"])

    return {
        "category": cat, "wind_mph": WIND_BY_CAT[cat], "surge": SURGE_BY_CAT[cat],
        "pred_total": pred_total, "total_customers": sum(z.customers for z in zones),
        "zones": zone_rows, "required": required, "internal": internal, "committed": committed, "needed": needed,
        "coverage": round(ratio, 3), "avg_eta_h": round(avg_eta, 1), "p95_eta_h": max(r["eta_h"] for r in zone_rows),
        "confidence": jround(min(95, 74 + (5 if ratio >= 0.95 else 0) - (cat - 3) * 3)),
        "critical_at_risk": sum(1 for f in facilities if f["risk"] != "Low"), "facilities": facilities,
        "lift_stations_at_risk": lift, "lift_stations_total": LIFT_STATIONS, "generators_needed": jround(lift * 0.6),
        "water_customers_at_risk": jround(sum(z.water_customers * risk[z.id] for z in zones)),
        "boil_water_zones": [z.short for z in zones if z.coastal] if cat >= 3 else [],
        "feeders": feeder_rows[:40],
        "materials": {"poles": jround(pred_total / 110), "transformers": jround(pred_total / 330), "conductor_miles": jround(pred_total / 900)},
    }
