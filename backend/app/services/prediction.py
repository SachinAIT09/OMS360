"""Storm impact prediction.

Inputs: storm intensity — one category / rainfall total for the territory, or the per-zone hazard from an
imported forecast (the parent company's storm model) — plus the utility's zones (customers, vulnerability),
circuits (overhead exposure, vegetation cycle, transformer age and health), the workforce on the roster and mutual
aid already requested. Output is stored as a PredictionRun so every forecast is reproducible and auditable.

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
                           × asset factor, asset factor = 1 + 0.6 × (1 − transformer health index / 100)
  restoration hours      = zone hours × circuit exposure ÷ the zone's customer-weighted mean exposure,
                           exposure = 0.7 + 0.5 × overhead% + 0.05 × years since trim (max 6)
                           + 0.15 × share of transformers in Poor/Critical condition (more replacements, not re-fusing)
  range                  = hours × (1 − u) … hours × (1 + 1.4u), u = 0.15 + 0.1 without a forecast
                           + 0.2 × crew shortfall + 0.1 × overhead% + 0.5 × share of the circuit predicted out
                           + 0.05 × Poor/Critical transformer share (wider where more can go wrong; u capped at 0.45)
  regions                = customer-weighted mean hours, last circuit expected and its upper bound

Tornadoes are built bottom-up from the circuits, because a damage path is a few hundred metres wide: two circuits out of
the same substation can see total destruction and nothing at all. For each circuit, d = closest approach of its route
to any damage path (km), w = that path's width:
  core(circuit)   = EF damage factor × exp(−max(0, d − w/2) / 0.4 km)      direct tornado damage (poles, transformers)
  fringe(circuit) = 0.05 × exp(−d / 25 km)                                  parent-supercell hail and straight-line winds
  predicted out   = customers × min(0.97, (1 − (1 − core)(1 − fringe)) × (0.55 + 0.45 × overhead%)
                    × (0.85 + 0.3 × vulnerability) × asset factor)
  restoration hrs = (10 + 96 × core^0.7 × (0.8 + 0.4 × overhead%) + 3 × years since trim + asset term) / coverage^0.75
                    — circuits in the core path are rebuilt, not repaired
  line workers    = customers out / 185, except the ~20% of a crossed circuit inside the path: / 60 (rebuild, not repair)
Zones and regions are the sums of their circuits. Before touchdown the paths are a planning case, so ranges are wider.
"""
import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..data import CATF, EF_DAMAGE, EF_WIDTH_M, EF_WIND, LIFT_STATIONS, SURGE_BY_CAT, WIND_BY_CAT
from ..fmt import jround
from ..models import Crew, Facility, Feeder, MutualAidRequest, StormEvent, Zone, utcnow
from .events import hazard

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


def _asset_factors(s: Session) -> dict[str, dict]:
    from .assets import circuit_factors
    return circuit_factors(s)


def _crew_plan(s: Session, event: StormEvent, req_line: int, tree_ratio: float, pred_total: int) -> dict:
    internal = workforce(s)
    committed = mutual_aid_committed(s, event.id)
    required = {"line": req_line, "tree": jround(req_line * tree_ratio), "da": max(20, jround(pred_total / 2500))}
    needed = {k: max(0, jround(required[k] * 1.08) - internal[k] - committed[k]) for k in required}
    supply_line = internal["line"] + committed["line"]
    ratio = min(1.1, supply_line / max(1, req_line))
    return {"internal": internal, "committed": committed, "required": required, "needed": needed, "ratio": ratio}


def predict(s: Session, event: StormEvent, category: int | None = None, rain_in: float | None = None,
            use_forecast: bool = True) -> dict:
    """An explicit category / rainfall is a what-if scenario for the whole territory; otherwise the latest imported
    forecast (if any, and use_forecast) gives each zone its own hazard."""
    from .forecast import latest_forecast
    kind = hazard(event)
    zones = s.scalars(select(Zone)).all()
    fc = latest_forecast(s, event.id) if use_forecast and category is None and rain_in is None else None
    hz = {h["zone_id"]: h for h in fc.zones} if fc else {}
    if kind == "tornado":
        return _predict_tornado(s, event, zones, category, fc, hz)
    rain = kind == "rain"
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

    plan = _crew_plan(s, event, jround(pred_total / 185), 0.6 if rain else 0.45, pred_total)
    ratio = plan["ratio"]

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
    risk = {r["id"]: r["pct"] for r in zone_rows}
    lift = jround(LIFT_STATIONS * min(0.6, cf * (1.6 if rain else 1.1)))  # flooding hits lift stations harder

    assets = _asset_factors(s)
    circuits, regions = _circuits(s, zones, preds, {r["id"]: r for r in zone_rows}, ratio, bool(fc), 0.6 if rain else 0.45, assets)

    if rain:
        confidence = min(95, 78 + (5 if ratio >= 0.95 else 0) - (4 if rain_in > 8 else 0) + (4 if fc else 0))
        boil = [z.short for z in zones if z.coastal] if max([rain_in] + [h["rain_in"] for h in hz.values() if h.get("rain_in")]) >= 8 else []
    else:
        confidence = min(95, 74 + (5 if ratio >= 0.95 else 0) - (cat - 3) * 3 + (4 if fc else 0))
        boil = [z.short for z in zones if z.coastal] if cat >= 3 else []
    xf = _transformers_needed(circuits, assets)
    return {
        "kind": "rain" if rain else "wind", "scenario": scenario, "rain_in": rain_in if rain else None,
        "forecast": {"id": fc.id, "source": fc.source, "issued_at": fc.issued_at.isoformat()} if fc else None,
        "category": cat, "wind_mph": event.max_wind_mph if rain else WIND_BY_CAT[cat], "surge": None if rain else SURGE_BY_CAT[cat],
        **_tail(s, zones, zone_rows, circuits, regions, plan, pred_total, risk, lift, confidence, boil),
        "materials": {"poles": jround(pred_total / (160 if rain else 110)), "transformers": xf if xf is not None else jround(pred_total / 330),
                      "conductor_miles": jround(pred_total / 900)},
    }


def _tail(s: Session, zones: list[Zone], zone_rows: list[dict], circuits: list[dict], regions: list[dict], plan: dict, pred_total: int,
          risk: dict, lift: int, confidence: float, boil: list[str], circuit_risk: dict | None = None) -> dict:
    """The parts of a prediction every hazard shares: crews, ETAs, critical facilities, water and circuits."""
    avg_eta = sum(r["eta_h"] * r["pred"] for r in zone_rows) / pred_total
    facilities = []
    for f in s.scalars(select(Facility)).all():
        pct = circuit_risk.get(f.feeder_id, risk[f.zone_id]) if circuit_risk else risk[f.zone_id]
        facilities.append({"id": f.id, "name": f.name, "kind": f.kind, "type": f.type, "feeder": f.feeder_id, "backup": f.backup,
                           "risk": "High" if pct > 0.4 else "Medium" if pct > 0.2 else "Low"})
    return {
        "pred_total": pred_total, "total_customers": sum(z.customers for z in zones),
        "zones": zone_rows, "required": plan["required"], "internal": plan["internal"], "committed": plan["committed"],
        "needed": plan["needed"], "coverage": round(plan["ratio"], 3), "avg_eta_h": round(avg_eta, 1),
        "p95_eta_h": max(r["eta_h"] for r in zone_rows), "confidence": jround(confidence),
        "critical_at_risk": sum(1 for f in facilities if f["risk"] != "Low"), "facilities": facilities,
        "lift_stations_at_risk": lift, "lift_stations_total": LIFT_STATIONS, "generators_needed": jround(lift * 0.6),
        "water_customers_at_risk": jround(sum(z.water_customers * risk[z.id] for z in zones)),
        "boil_water_zones": boil,
        "feeders": [{"id": c["id"], "zone": c["zone"], "pred": c["pred"]} for c in circuits[:40]],
        "circuits": circuits, "regions": regions,
    }


REPLACE_RATE = 0.022  # transformers replaced per transformer on an outaged circuit (≈ 1 per 330 customers out at 10 per transformer)
CORE_SECTION = 0.2    # share of a crossed circuit inside the damage path: the section that is rebuilt, not repaired


def _transformers_needed(circuits: list[dict], assets: dict, core: dict | None = None) -> int | None:
    """Distribution transformers to replace, from each circuit's own transformer count: the replacement rate on the circuit's
    share out, raised 2.5× for units in Poor/Critical condition, plus the units destroyed where a tornado core crosses.
    None when no asset register is loaded (callers fall back to the per-customer rule of thumb)."""
    if not assets:
        return None
    n = 0.0
    for c in circuits:
        a = assets.get(c["id"])
        if not a or not c["customers"]:
            continue
        share = c["pred"] / c["customers"]
        destroyed = CORE_SECTION * core.get(c["id"], 0) if core else 0
        n += a["xfmrs"] * min(0.9, share * REPLACE_RATE * (1 + 2.5 * a["poor"]) + destroyed)
    return jround(n)


def _years_since_trim(f: Feeder) -> int:
    return max(0, utcnow().year - f.last_trimmed)


def _circuits(s: Session, zones: list[Zone], preds: dict, zone_rows: dict, ratio: float, has_forecast: bool,
              tree_ratio: float, assets: dict | None = None) -> tuple[list, list]:
    """Predicted customers out and restoration hours (with a range) per circuit, rolled up to regions with the crews each
    region needs (same 185 customers per line worker as the territory total) so crews can be staged by region."""
    from .ops import network_index
    idx = network_index(s)
    assets = assets or {}
    feeders = s.scalars(select(Feeder)).all()
    zmap = {z.id: z for z in zones}
    years = {f.id: _years_since_trim(f) for f in feeders}
    poor = {f.id: assets.get(f.id, {}).get("poor", 0.0) for f in feeders}
    af = {f.id: 1 + 0.6 * (1 - assets[f.id]["hi"] / 100) if f.id in assets else 1.0 for f in feeders}
    w = {f.id: f.customers * (f.overhead_pct / 100) ** 2 * zmap[f.zone_id].vulnerability ** 3 * (years[f.id] + 1) * af[f.id] for f in feeders}
    expo = {f.id: 0.7 + 0.5 * f.overhead_pct / 100 + 0.05 * min(6, years[f.id]) + 0.15 * poor[f.id] for f in feeders}
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
        u = min(0.45, 0.15 + (0 if has_forecast else 0.1) + 0.2 * shortfall + 0.1 * f.overhead_pct / 100 + 0.5 * share
                + 0.05 * poor[f.id])  # heavier damage, wider range
        rows.append(_circuit_row(f, info, z["short"], pred, share, eta, u, years[f.id], assets.get(f.id)))
    rows.sort(key=lambda r: -r["pred"])
    return rows, _regions(rows, idx, tree_ratio)


def _circuit_row(f: Feeder, info: dict, zone_short: str, pred: int, share: float, eta: float, u: float, years: int,
                 asset: dict | None, extra: dict | None = None) -> dict:
    row = {"id": f.id, "zone_id": f.zone_id, "zone": zone_short, "substation": info.get("substation"),
           "region_id": info.get("region_id"), "region": info.get("region"), "customers": f.customers, "pred": pred,
           "pct": round(share, 4), "eta_h": round(eta, 1),
           "low_h": round(eta * (1 - u), 1), "high_h": round(eta * (1 + 1.4 * u), 1),
           "confidence": jround(max(40, min(92, 100 - u * 110))), "overhead_pct": f.overhead_pct, "years_since_trim": years}
    if asset:
        row |= {"asset_hi": round(asset["hi"], 1), "pct_poor": round(asset["poor"], 3), "mean_xfmr_age": round(asset["age"], 1),
                "xfmrs": asset["xfmrs"]}
    return row | (extra or {})


def _regions(rows: list[dict], idx: dict, tree_ratio: float, line_of=None) -> list[dict]:
    """Roll circuits up to their regions: customers out, the line and tree workers to stage there, and restoration hours."""
    line_of = line_of or (lambda cs: sum(c["pred"] for c in cs) / 185)
    regions = []
    by_region: dict[str, list] = {}
    for r in rows:
        by_region.setdefault(r["region_id"], []).append(r)
    names = {i["region_id"]: i["region"] for i in idx.values()}
    for rid, cs in sorted(by_region.items(), key=lambda kv: str(kv[0])):
        out = sum(c["pred"] for c in cs) or 1
        last = max(cs, key=lambda c: c["eta_h"])
        line = jround(line_of(cs))
        regions.append({"id": rid, "name": names.get(rid) or "Unassigned", "pred": sum(c["pred"] for c in cs), "circuits": len(cs),
                        "line_workers": line, "tree_workers": jround(line * tree_ratio),
                        "eta_h": round(sum(c["eta_h"] * c["pred"] for c in cs) / out, 1),
                        "low_h": round(sum(c["low_h"] * c["pred"] for c in cs) / out, 1),
                        "high_h": round(sum(c["high_h"] * c["pred"] for c in cs) / out, 1),
                        "last_h": last["eta_h"], "last_high_h": max(c["high_h"] for c in cs),
                        "confidence": jround(sum(c["confidence"] * c["pred"] for c in cs) / out),
                        "circuits_in_path": sum(1 for c in cs if c.get("in_path")),
                        "xfmrs_in_path": sum(c.get("xfmrs", 0) for c in cs if c.get("in_path"))})
    return regions


# ---------------------------------------------------------------- tornadoes
def tornado_paths(event: StormEvent, category: int | None = None) -> list[dict]:
    """The event's damage paths from its track: [{ef, width_m, points [(lat, lng)], at [iso]}]. A what-if category moves every
    path's EF rating by the same number of steps as the event's own rating."""
    by: dict[int, dict] = {}
    for p in event.track or []:
        i = p.get("path", 0)
        d = by.setdefault(i, {"ef": p.get("ef", event.category), "width_m": p.get("width_m"), "points": [], "at": []})
        d["points"].append((p["lat"], p["lng"]))
        d["at"].append(p.get("at"))
    if not by:  # no path drawn yet: a short planning path through the event's position
        by[0] = {"ef": event.category, "width_m": None, "points": [(event.lat, event.lng), (event.lat + 0.12, event.lng + 0.18)], "at": [None, None]}
    shift = 0 if category is None else category - event.category
    out = []
    for d in by.values():
        ef = max(0, min(5, d["ef"] + shift))
        out.append(d | {"ef": ef, "width_m": d["width_m"] or EF_WIDTH_M[ef]})
    return out


def _xy(lat: float, lng: float, lat0: float) -> tuple[float, float]:
    return lng * 111.32 * math.cos(math.radians(lat0)), lat * 110.57


def _seg_point(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _seg_seg(a, b, c, d) -> float:
    """Shortest distance between segments ab and cd (planar km); 0 when they cross."""
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
        return 0.0
    return min(_seg_point(*a, *c, *d), _seg_point(*b, *c, *d), _seg_point(*c, *a, *b), _seg_point(*d, *a, *b))


def path_distance_km(route: list, points: list[tuple[float, float]], lat0: float) -> float:
    """Closest approach (km) of a circuit route (list of polylines) to a damage path (polyline)."""
    path = [_xy(la, ln, lat0) for la, ln in points]
    best = math.inf
    for line in route or []:
        pts = [_xy(p[0], p[1], lat0) for p in line]
        if len(pts) == 1:
            pts = pts * 2
        for a, b in zip(pts, pts[1:]):
            for c, d in zip(path, path[1:]):
                best = min(best, _seg_seg(a, b, c, d))
                if best == 0:
                    return 0.0
    return best


def _predict_tornado(s: Session, event: StormEvent, zones: list[Zone], category: int | None, fc, hz: dict) -> dict:
    from .ops import network_index
    paths = tornado_paths(event, category)
    ef = max(p["ef"] for p in paths)
    lat0 = sum(z.lat for z in zones) / len(zones)
    idx = network_index(s)
    assets = _asset_factors(s)
    zmap = {z.id: z for z in zones}
    feeders = s.scalars(select(Feeder)).all()
    touched_down = bool(event.track) and all(p.get("observed") for p in event.track)

    per: dict[str, dict] = {}
    for f in feeders:
        z = zmap[f.zone_id]
        route = f.route or [[[z.lat, z.lng]]]
        best = {"d": math.inf, "core": 0.0, "path": None}
        fringe = 0.0
        for i, p in enumerate(paths):
            d = path_distance_km(route, p["points"], lat0)
            core = EF_DAMAGE[p["ef"]] * math.exp(-max(0.0, d - p["width_m"] / 2000) / 0.4)
            fringe = max(fringe, 0.05 * math.exp(-d / 25) * (0.6 + 0.1 * p["ef"]))
            if core > best["core"] or (best["path"] is None and d < best["d"]):
                best = {"d": d, "core": core, "path": i}
        h = hz.get(f.zone_id)
        if h and h.get("gust_mph"):  # an imported forecast's straight-line winds (capped below tornado strength)
            fringe = max(fringe, 0.5 * wind_factor(min(h["gust_mph"], 95)))
        per[f.id] = best | {"fringe": fringe}

    rows_raw = []
    for f in feeders:
        z, p = zmap[f.zone_id], per[f.id]
        oh = f.overhead_pct / 100
        a = assets.get(f.id)
        af = 1 + 0.6 * (1 - a["hi"] / 100) if a else 1.0
        hz_f = 1 - (1 - p["core"]) * (1 - p["fringe"])
        pred = jround(f.customers * min(0.97, hz_f * (0.55 + 0.45 * oh) * (0.85 + 0.3 * z.vulnerability) * af))
        core_out = jround(pred * min(1.0, p["core"] / hz_f) * CORE_SECTION) if hz_f else 0  # customers in the section to rebuild
        rows_raw.append((f, z, p, pred, core_out, oh, a))
    pred_total = sum(r[3] for r in rows_raw) or 1
    core_total = sum(r[4] for r in rows_raw)
    req_line = jround((pred_total - core_total) / 185 + core_total / 60)
    plan = _crew_plan(s, event, req_line, 0.5, pred_total)
    ratio = plan["ratio"]
    shortfall = max(0.0, 1 - ratio)

    circuits = []
    for f, z, p, pred, core_out, oh, a in rows_raw:  # noqa: B007
        years = _years_since_trim(f)
        poor = a["poor"] if a else 0.0
        eta = (10 + 96 * p["core"] ** 0.7 * (0.8 + 0.4 * oh) + 3 * min(6, years) + 20 * poor * min(1, p["core"] * 3 + 0.2)) \
            / math.pow(min(1, ratio), 0.75)
        share = pred / f.customers if f.customers else 0
        u = min(0.6, 0.2 + (0 if touched_down else 0.15) + (0 if fc else 0.05) + 0.2 * shortfall + 0.15 * p["core"] + 0.05 * poor)
        in_path = p["core"] >= 0.25
        path = paths[p["path"]] if p["path"] is not None else None
        circuits.append(_circuit_row(f, idx.get(f.id, {}), z.short, pred, share, eta, u, years, a, {
            "in_path": in_path, "path_km": round(p["d"], 2) if p["d"] != math.inf else None, "core": round(p["core"], 3),
            "path_ef": path["ef"] if path else None, "rebuild_out": core_out}))
    circuits.sort(key=lambda r: -r["pred"])
    core_by = {c["id"]: c["core"] for c in circuits}
    regions = _regions(circuits, idx, 0.5, lambda cs: sum(c["pred"] - c["rebuild_out"] for c in cs) / 185 + sum(c["rebuild_out"] for c in cs) / 60)

    # zones are the sums of their circuits
    zone_rows, risk, zf = [], {}, {}
    for z in zones:
        cs = [c for c in circuits if c["zone_id"] == z.id]
        pred = sum(c["pred"] for c in cs)
        cores = [c["core"] for c in cs] or [0.0]
        fringe = max((per[c["id"]]["fringe"] for c in cs), default=0.0)
        eta = sum(c["eta_h"] * c["pred"] for c in cs) / pred if pred else 8
        path_i = next((per[c["id"]]["path"] for c in sorted(cs, key=lambda c: -c["core"])), None)
        path = paths[path_i] if path_i is not None else None
        hit = max(cores) >= 0.25
        driver = (f"Direct tornado path (EF{path['ef']}) — rebuild" if hit and path else "Edge of tornado path + hail" if max(cores) > 0.02
                  else "Hail + straight-line winds" if fringe > 0.01 else "Outside the storm area")
        gust = max(EF_WIND[path["ef"]] * max(cores) / EF_DAMAGE[path["ef"]] if path else 0, 35 + 700 * fringe)
        nearest = min((per[c["id"]]["d"] for c in cs), default=math.inf)
        h = hz.get(z.id)
        risk[z.id] = round(pred / z.customers, 4) if z.customers else 0
        zf[z.id] = pred / z.customers if z.customers else 0
        zone_rows.append({"id": z.id, "name": z.name, "short": z.short, "customers": z.customers, "pred": pred, "pct": risk[z.id],
                          "eta_h": max(6, jround(eta)), "driver": driver,
                          "circuits_in_path": sum(1 for c in cs if c["in_path"]),
                          "hazard": {"gust_mph": round(h["gust_mph"]) if h and h.get("gust_mph") else round(min(EF_WIND[5], gust)),
                                     "path_km": round(nearest, 1) if nearest != math.inf else None,
                                     **({"arrival_at": h["arrival_at"]} if h and h.get("arrival_at") else {})}})
    cf = sum(zf[z.id] * z.customers for z in zones) / sum(z.customers for z in zones)
    lift = jround(LIFT_STATIONS * min(0.6, cf * 1.1))
    confidence = min(92, 60 + (5 if ratio >= 0.95 else 0) + (14 if touched_down else 0) + (4 if fc else 0) - max(0, ef - 3) * 3)
    in_path = [c for c in circuits if c["in_path"]]
    xf = _transformers_needed(circuits, assets, core_by)
    poles = jround(core_total / 6 + (pred_total - core_total) / 180)  # in the path roughly one pole per six customers is down
    path_rows = []
    for i, p in enumerate(paths):
        length = sum(math.hypot(*(a - b for a, b in zip(_xy(*p1, lat0), _xy(*p2, lat0)))) for p1, p2 in zip(p["points"], p["points"][1:]))
        hit = [c for c in in_path if per[c["id"]]["path"] == i]
        path_rows.append({"ef": p["ef"], "width_m": p["width_m"], "length_km": round(length, 1), "circuits_hit": len(hit),
                          "customers_in_path": sum(c["customers"] for c in hit), "xfmrs_in_path": sum(c.get("xfmrs", 0) for c in hit),
                          "start_at": p["at"][0] if p.get("at") else None})
    return {
        "kind": "tornado", "scenario": f"{fc.source} forecast + EF{ef}" if fc else f"EF{ef} · " + ("surveyed paths" if touched_down else "planning paths"),
        "rain_in": None, "forecast": {"id": fc.id, "source": fc.source, "issued_at": fc.issued_at.isoformat()} if fc else None,
        "category": ef, "ef": ef, "wind_mph": EF_WIND[ef], "surge": None, "paths": path_rows,
        "circuits_in_path": len(in_path), "customers_in_path": sum(c["customers"] for c in in_path),
        **_tail(s, zones, zone_rows, circuits, regions, plan, pred_total, risk, lift, confidence, [], {c["id"]: c["pct"] for c in circuits}),
        "materials": {"poles": poles, "transformers": xf if xf is not None else jround(core_total / 12 + (pred_total - core_total) / 330),
                      "conductor_miles": jround(core_total / 150 + (pred_total - core_total) / 900)},
    }
