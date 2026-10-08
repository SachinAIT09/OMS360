"""Storm impact prediction.

Inputs: storm intensity — one category / rainfall total for the territory, or the per-zone hazard from an
imported forecast (the parent company's storm model) — plus the utility's zones (customers, vulnerability),
circuits (overhead exposure, vegetation cycle), the workforce on the roster and mutual aid already requested.
Output is stored as a PredictionRun so every forecast is reproducible and auditable.

  predicted out(zone) = customers × min(0.97, hazardFactor(zone) × vulnerability × 1.15 × surge boost)
  line workers needed  = predicted total / 185  (customers restored per worker per event,
                         calibrated on Irma 2017 / Ian 2022 / Milton 2024 damage in the territory)
  restoration hours    = (14 + hazardFactor × 95 × vuln − critical bonus) / coverage^0.75

  hazardFactor = category factor (CATF), or from the forecast peak gust at the zone (gust ÷ 1.25 = sustained wind,
                 interpolated on the same category curve); coastal zones × (1 + 0.03 × forecast surge ft)

Rain events replace the category factor with a rainfall factor (per zone when a forecast gives zone rainfall):
  rainFactor = 0.012 × rainfall(in) × (0.6 + 0.8 × soil saturation) × (1 + 0.15 × (peak rate − 1 in/hr))
  predicted out(zone)  = customers × min(0.9, rainFactor × vulnerability × 1.15 × 1.3 if low-lying/coastal)
  restoration hours    = (10 + rainFactor × 120 × vuln + 8 flood-access delay if coastal − critical bonus) / coverage^0.75

Circuits (feeders) — the level customers are told about:
  predicted out(circuit) = zone prediction shared by customers × overhead%² × vulnerability³ × years since trim
  restoration hours      = zone hours × circuit exposure ÷ the zone's customer-weighted mean exposure,
                           exposure = 0.7 + 0.5 × overhead% + 0.05 × years since trim (max 6)
  range                  = hours × (1 − u) … hours × (1 + 1.4u), u = 0.15 + 0.1 without a forecast
                           + 0.2 × crew shortfall + 0.1 × overhead% + 0.5 × share of the circuit predicted out
                           (wider where more can go wrong; u capped at 0.45)
  regions                = customer-weighted mean hours, last circuit expected and its upper bound
"""
import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..data import CATF, LIFT_STATIONS, SURGE_BY_CAT, WIND_BY_CAT
from ..fmt import jround
from ..models import Crew, Facility, Feeder, MutualAidRequest, StormEvent, Zone
from .events import is_rain

# sustained wind (mph) → damage factor; CATF / WIND_BY_CAT points plus tropical-storm and extreme ends
WIND_CURVE = [(39, 0.0), (65, 0.03)] + [(WIND_BY_CAT[c], CATF[c]) for c in range(1, 6)] + [(200, 0.9)]


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


def rain_factor(rain_in: float, rate_in_hr: float, saturation: float) -> float:
    return min(0.45, max(0.01, 0.012 * rain_in * (0.6 + 0.8 * saturation) * (1 + 0.15 * max(0.0, rate_in_hr - 1))))


def wind_factor(gust_mph: float) -> float:
    sustained = gust_mph / 1.25
    if sustained <= WIND_CURVE[0][0]:
        return 0.0
    for (w0, f0), (w1, f1) in zip(WIND_CURVE, WIND_CURVE[1:]):
        if sustained <= w1:
            return f0 + (f1 - f0) * (sustained - w0) / (w1 - w0)
    return WIND_CURVE[-1][1]


def _rain_driver(z: Zone) -> str:
    return ("Flooding + saturated-soil tree falls" if z.coastal else "Saturated soil + dense tree canopy" if z.vulnerability > 0.75
            else "Tree falls on aging overhead lines" if z.vulnerability > 0.6 else "Flooded underground equipment")


def _wind_driver(z: Zone) -> str:
    return ("Storm surge + wind" if z.coastal else "Wind + dense tree canopy" if z.vulnerability > 0.75
            else "Wind + aging overhead lines" if z.vulnerability > 0.6 else "Wind (mostly underground)")


def predict(s: Session, event: StormEvent, category: int | None = None, rain_in: float | None = None,
            use_forecast: bool = True) -> dict:
    """An explicit category / rainfall is a what-if scenario for the whole territory; otherwise the latest imported
    forecast (if any, and use_forecast) gives each zone its own hazard."""
    from .forecast import latest_forecast
    rain = is_rain(event)
    zones = s.scalars(select(Zone)).all()
    fc = latest_forecast(s, event.id) if use_forecast and category is None and rain_in is None else None
    hz = {h["zone_id"]: h for h in fc.zones} if fc else {}
    sat = 0.5 if event.soil_saturation is None else event.soil_saturation
    rate = event.rain_rate_in_hr or 1.0

    if rain:
        cat = 1
        rain_in = rain_in or event.rain_total_in or 4.0
        zf = {z.id: rain_factor(hz[z.id]["rain_in"] if z.id in hz else rain_in, rate, sat) for z in zones}
        preds = {z.id: jround(z.customers * min(0.9, zf[z.id] * z.vulnerability * 1.15 * (1.3 if z.coastal else 1))) for z in zones}
        scenario = f"{fc.source} forecast" if fc else f"{rain_in:g} in rain"
    else:
        cat = max(1, min(5, category or event.category or 1))  # the advisory category; a forecast varies it by zone
        zf = {z.id: wind_factor(hz[z.id]["gust_mph"]) if z.id in hz else CATF[cat] for z in zones}
        surge = {z.id: 1 + 0.03 * (hz.get(z.id, {}).get("surge_ft") or 0) if z.coastal else 1 for z in zones}
        preds = {z.id: jround(z.customers * min(0.97, zf[z.id] * z.vulnerability * 1.15 * surge[z.id])) for z in zones}
        scenario = f"{fc.source} forecast" if fc else f"Cat {cat}"
    pred_total = sum(preds.values()) or 1
    cf = sum(zf[z.id] * z.customers for z in zones) / sum(z.customers for z in zones)  # territory-wide hazard

    internal = workforce(s)
    committed = mutual_aid_committed(s, event.id)
    req_line = jround(pred_total / 185)
    required = {"line": req_line, "tree": jround(req_line * (0.6 if rain else 0.45)), "da": max(20, jround(pred_total / 2500))}
    needed = {k: max(0, jround(required[k] * 1.08) - internal[k] - committed[k]) for k in required}
    supply_line = internal["line"] + committed["line"]
    ratio = min(1.1, supply_line / max(1, req_line))

    zone_rows = []
    for z in zones:
        f = zf[z.id]
        if rain:
            eta = (10 + f * 120 * z.vulnerability + (8 if z.coastal else 0) - (6 if z.critical else 0)) / math.pow(min(1, ratio), 0.75)
        else:
            eta = (14 + f * 95 * z.vulnerability - (6 if z.critical else 0)) / math.pow(min(1, ratio), 0.75)
        h = hz.get(z.id)
        zone_rows.append({"id": z.id, "name": z.name, "short": z.short, "customers": z.customers, "pred": preds[z.id],
                          "pct": round(preds[z.id] / z.customers, 4), "eta_h": max(8 if rain else 12, jround(eta)),
                          "driver": _rain_driver(z) if rain else _wind_driver(z),
                          "hazard": {k: h[k] for k in ("gust_mph", "rain_in", "surge_ft", "arrival_at") if k in h} if h else None})
    avg_eta = sum(r["eta_h"] * r["pred"] for r in zone_rows) / pred_total
    risk = {r["id"]: r["pct"] for r in zone_rows}
    facilities = [{"id": f.id, "name": f.name, "kind": f.kind, "type": f.type, "feeder": f.feeder_id, "backup": f.backup,
                   "risk": "High" if risk[f.zone_id] > 0.4 else "Medium" if risk[f.zone_id] > 0.2 else "Low"}
                  for f in s.scalars(select(Facility)).all()]
    lift = jround(LIFT_STATIONS * min(0.6, cf * (1.6 if rain else 1.1)))  # flooding hits lift stations harder

    circuits, regions = _circuits(s, zones, preds, {r["id"]: r for r in zone_rows}, ratio, bool(fc))

    if rain:
        confidence = min(95, 78 + (5 if ratio >= 0.95 else 0) - (4 if rain_in > 8 else 0) + (4 if fc else 0))
        boil = [z.short for z in zones if z.coastal] if max([rain_in] + [h["rain_in"] for h in hz.values() if h.get("rain_in")]) >= 8 else []
    else:
        confidence = min(95, 74 + (5 if ratio >= 0.95 else 0) - (cat - 3) * 3 + (4 if fc else 0))
        boil = [z.short for z in zones if z.coastal] if cat >= 3 else []
    return {
        "kind": "rain" if rain else "wind", "scenario": scenario, "rain_in": rain_in if rain else None,
        "forecast": {"id": fc.id, "source": fc.source, "issued_at": fc.issued_at.isoformat()} if fc else None,
        "category": cat, "wind_mph": event.max_wind_mph if rain else WIND_BY_CAT[cat], "surge": None if rain else SURGE_BY_CAT[cat],
        "pred_total": pred_total, "total_customers": sum(z.customers for z in zones),
        "zones": zone_rows, "required": required, "internal": internal, "committed": committed, "needed": needed,
        "coverage": round(ratio, 3), "avg_eta_h": round(avg_eta, 1), "p95_eta_h": max(r["eta_h"] for r in zone_rows),
        "confidence": jround(confidence),
        "critical_at_risk": sum(1 for f in facilities if f["risk"] != "Low"), "facilities": facilities,
        "lift_stations_at_risk": lift, "lift_stations_total": LIFT_STATIONS, "generators_needed": jround(lift * 0.6),
        "water_customers_at_risk": jround(sum(z.water_customers * risk[z.id] for z in zones)),
        "boil_water_zones": boil,
        "feeders": [{"id": c["id"], "zone": c["zone"], "pred": c["pred"]} for c in circuits[:40]],
        "circuits": circuits, "regions": regions,
        "materials": {"poles": jround(pred_total / (160 if rain else 110)), "transformers": jround(pred_total / 330), "conductor_miles": jround(pred_total / 900)},
    }


def _circuits(s: Session, zones: list[Zone], preds: dict, zone_rows: dict, ratio: float, has_forecast: bool) -> tuple[list, list]:
    """Predicted customers out and restoration hours (with a range) per circuit, rolled up to regions."""
    from .ops import network_index
    idx = network_index(s)
    feeders = s.scalars(select(Feeder)).all()
    zmap = {z.id: z for z in zones}
    years = {f.id: max(0, 2025 - f.last_trimmed) for f in feeders}
    w = {f.id: f.customers * (f.overhead_pct / 100) ** 2 * zmap[f.zone_id].vulnerability ** 3 * (years[f.id] + 1) for f in feeders}
    expo = {f.id: 0.7 + 0.5 * f.overhead_pct / 100 + 0.05 * min(6, years[f.id]) for f in feeders}
    wz: dict[str, float] = {}
    ez: dict[str, list[float]] = {}
    for f in feeders:
        wz[f.zone_id] = wz.get(f.zone_id, 0) + w[f.id]
        ez.setdefault(f.zone_id, [0.0, 0.0])
        ez[f.zone_id][0] += expo[f.id] * f.customers
        ez[f.zone_id][1] += f.customers
    shortfall = max(0.0, 1 - ratio)
    rows = []
    for f in feeders:
        z, info = zone_rows[f.zone_id], idx.get(f.id, {})
        pred = jround(preds[f.zone_id] * w[f.id] / wz[f.zone_id]) if wz[f.zone_id] else 0
        eta = z["eta_h"] * expo[f.id] / (ez[f.zone_id][0] / ez[f.zone_id][1])
        share = pred / f.customers if f.customers else 0
        u = min(0.45, 0.15 + (0 if has_forecast else 0.1) + 0.2 * shortfall + 0.1 * f.overhead_pct / 100 + 0.5 * share)  # heavier damage, wider range
        rows.append({"id": f.id, "zone_id": f.zone_id, "zone": z["short"], "substation": info.get("substation"),
                     "region_id": info.get("region_id"), "region": info.get("region"), "customers": f.customers, "pred": pred,
                     "pct": round(share, 4), "eta_h": round(eta, 1),
                     "low_h": round(eta * (1 - u), 1), "high_h": round(eta * (1 + 1.4 * u), 1),
                     "confidence": jround(max(40, min(92, 100 - u * 110))), "overhead_pct": f.overhead_pct, "years_since_trim": years[f.id]})
    rows.sort(key=lambda r: -r["pred"])
    regions = []
    by_region: dict[str, list] = {}
    for r in rows:
        by_region.setdefault(r["region_id"], []).append(r)
    names = {i["region_id"]: i["region"] for i in idx.values()}
    for rid, cs in sorted(by_region.items(), key=lambda kv: str(kv[0])):
        out = sum(c["pred"] for c in cs) or 1
        last = max(cs, key=lambda c: c["eta_h"])
        regions.append({"id": rid, "name": names.get(rid) or "Unassigned", "pred": sum(c["pred"] for c in cs), "circuits": len(cs),
                        "eta_h": round(sum(c["eta_h"] * c["pred"] for c in cs) / out, 1),
                        "low_h": round(sum(c["low_h"] * c["pred"] for c in cs) / out, 1),
                        "high_h": round(sum(c["high_h"] * c["pred"] for c in cs) / out, 1),
                        "last_h": last["eta_h"], "last_high_h": max(c["high_h"] for c in cs),
                        "confidence": jround(sum(c["confidence"] * c["pred"] for c in cs) / out)})
    return rows, regions
