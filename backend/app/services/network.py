"""Circuit (feeder) routes for maps.

A route is a list of polylines [[[lat, lng], ...], ...]: the primary conductor path of the feeder.
  synthetic — the sandbox draws each feeder out from its substation along a street-grid-like path;
  imported  — the utility's GIS export (GeoJSON, WGS84) replaces it, matched by feeder ID.
"""
import math
import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Feeder, Substation, Zone

ID_KEYS = ("feeder_id", "feeder", "circuit_id", "circuit", "feederid", "circuitid", "fdr", "id", "name")
SUB_KEYS = ("substation", "substation_id", "sub", "sub_name", "substation_name")
CUST_KEYS = ("customers", "customer_count", "cust", "num_customers", "meters")


class RouteError(ValueError):
    pass


def _synthetic(f: Feeder, sub_lat: float, sub_lng: float, slot: int, slots: int, rng: random.Random) -> list:
    """From the substation outward on a heading spread around the compass, moving along a north–south / east–west
    grid with occasional jogs; bigger feeders run longer and get a lateral branch."""
    heading = 2 * math.pi * (slot + rng.uniform(0.15, 0.85)) / max(1, slots)
    dlat, dlng = math.sin(heading), math.cos(heading)
    steps = min(14, 5 + f.customers // 1500)
    lat, lng = sub_lat, sub_lng
    main = [[round(lat, 5), round(lng, 5)]]
    for i in range(steps):
        step = rng.uniform(0.004, 0.008)
        if i % 2 == 0 or rng.random() < 0.3:  # run along the dominant axis, then jog along the other
            if abs(dlat) > abs(dlng):
                lat += math.copysign(step, dlat)
            else:
                lng += math.copysign(step, dlng)
        else:
            if abs(dlat) > abs(dlng):
                lng += math.copysign(step * abs(dlng) * 1.6 + 0.001, dlng)
            else:
                lat += math.copysign(step * abs(dlat) * 1.6 + 0.001, dlat)
        main.append([round(lat, 5), round(lng, 5)])
    lines = [main]
    if f.customers > 4000 and len(main) > 4:  # a lateral off the middle of the trunk
        b_lat, b_lng = main[len(main) // 2]
        side = rng.choice([-1, 1])
        branch = [[b_lat, b_lng]]
        for _ in range(3):
            if abs(dlat) > abs(dlng):
                b_lng += side * rng.uniform(0.004, 0.007)
            else:
                b_lat += side * rng.uniform(0.004, 0.007)
            branch.append([round(b_lat, 5), round(b_lng, 5)])
        lines.append(branch)
    return lines


def ensure_routes(s: Session) -> int:
    """Synthetic routes for feeders that have none. Returns how many were drawn."""
    subs = {x.id: x for x in s.scalars(select(Substation)).all()}
    zones = {z.id: z for z in s.scalars(select(Zone)).all()}
    by_sub: dict[str, list[Feeder]] = {}
    for f in s.scalars(select(Feeder).order_by(Feeder.id)).all():
        by_sub.setdefault(f.substation_id or f.zone_id, []).append(f)
    n = 0
    for key, fs in by_sub.items():
        sub = subs.get(key)
        lat, lng = (sub.lat, sub.lng) if sub else (zones[fs[0].zone_id].lat, zones[fs[0].zone_id].lng)
        for i, f in enumerate(fs):
            if f.route:
                continue
            f.route, f.route_source = _synthetic(f, lat, lng, i, len(fs), random.Random(f.id)), "synthetic"
            n += 1
    s.flush()
    return n


def _prop(props: dict, keys: tuple[str, ...]):
    low = {str(k).lower(): v for k, v in (props or {}).items()}
    return next((low[k] for k in keys if low.get(k) not in (None, "")), None)


def _lines(geom: dict) -> list:
    t, coords = (geom or {}).get("type"), (geom or {}).get("coordinates")
    if t == "LineString":
        parts = [coords]
    elif t == "MultiLineString":
        parts = coords
    else:
        raise RouteError(f"Feeder geometry must be LineString or MultiLineString, got {t or 'nothing'}.")
    out = []
    for part in parts:
        line = []
        for pt in part:
            lng, lat = float(pt[0]), float(pt[1])
            if not (-180 <= lng <= 180 and -90 <= lat <= 90):
                raise RouteError("Coordinates look projected (for example State Plane feet). Export the layer as WGS84 / EPSG:4326 "
                                 "(QGIS: Export → Save Features As → GeoJSON, CRS EPSG:4326).")
            line.append([round(lat, 6), round(lng, 6)])
        if len(line) >= 2:
            out.append(line)
    return out


def import_geojson(s: Session, data: dict) -> dict:
    """Replace routes with the utility's GIS export, matched on feeder ID. Unknown feeder IDs are reported, not created."""
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise RouteError("Expected a GeoJSON FeatureCollection of feeder lines.")
    feeders = {f.id.upper(): f for f in s.scalars(select(Feeder)).all()}
    matched, unmatched, missing_id = 0, [], 0
    for feat in data["features"]:
        props = feat.get("properties") or {}
        fid = _prop(props, ID_KEYS)
        if fid is None:
            missing_id += 1
            continue
        f = feeders.get(str(fid).strip().upper())
        if not f:
            unmatched.append(str(fid))
            continue
        lines = _lines(feat.get("geometry"))
        if not lines:
            continue
        f.route = (f.route if f.route_source == "imported" else []) + lines  # a feeder may arrive as several features
        f.route_source = "imported"
        cust = _prop(props, CUST_KEYS)
        if cust not in (None, ""):
            try:
                f.customers = max(1, int(float(cust)))
            except ValueError:
                pass
        matched += 1
    if not matched:
        hint = f" First IDs in the file: {', '.join(unmatched[:5])}." if unmatched else ""
        raise RouteError("No feeder in the file matched a circuit ID in OMS360. Each feature needs a property such as "
                         f"feeder_id or circuit holding the same ID the outage system uses.{hint}")
    s.flush()
    return {"matched": matched, "unmatched": len(unmatched), "unmatched_ids": unmatched[:20], "missing_id": missing_id}


def routes(s: Session) -> dict:
    subs = {x.id: x for x in s.scalars(select(Substation)).all()}
    zones = {z.id: z.short for z in s.scalars(select(Zone)).all()}
    rows = [{"id": f.id, "zone": zones.get(f.zone_id), "substation": subs[f.substation_id].name if f.substation_id in subs else None,
             "source": f.route_source, "route": f.route or []} for f in s.scalars(select(Feeder).order_by(Feeder.id)).all()]
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["source"] or "none"] = counts.get(r["source"] or "none", 0) + 1
    return {"feeders": rows, "counts": counts,
            "substations": [{"id": x.id, "name": x.name, "lat": x.lat, "lng": x.lng} for x in subs.values()]}
