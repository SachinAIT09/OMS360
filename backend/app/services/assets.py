"""Asset register, rollups and planning for major equipment: substation power transformers, distribution transformers,
feeder breakers, line reclosers and distribution poles. The health model itself is in asset_model.py (illustrative,
adjustable weights).

Hierarchy: region → substation (power transformers, feeder breakers) → circuit (distribution transformers, reclosers,
poles) → unit. The sandbox seeds a synthetic register (deterministic per circuit and substation; `source` = "sandbox")
until the utility imports its own (Asset health → Import asset register, CSV). A small share of sandbox records
deliberately lack an install year or an inspection, so the missing-data handling is visible.
Density: OMS360_ASSET_DENSITY customers per distribution transformer (default 10); poles scale with it.
"""
import csv
import io
import math
import os
import random
import zlib

from sqlalchemy import Integer, case, cast, delete, func, insert, select
from sqlalchemy.orm import Session

from ..models import Asset, AssetEvent, Facility, Feeder, Region, Substation, WorkOrder, Zone, utcnow
from .asset_model import (BREAKER, DIST, KINDS, POLE, POOR, POWER, RECLOSER, SETTING_KEY, SWITCHGEAR, load_weights,  # noqa: F401
                          methodology, score as _score, validate_weights)

BANDS = (("Good", 70), ("Fair", 50), ("Poor", 30), ("Critical", 0))
CONDITIONS = ("Good", "Fair", "Poor", "Critical", "Unknown")
MAKERS_POWER = ["GE", "Westinghouse", "ABB", "Siemens", "Hitachi Energy", "SPX Waukesha", "Virginia Transformer", "Howard"]
MAKERS_DIST = ["Howard", "ERMCO", "Eaton", "GE", "Westinghouse", "ABB", "Central Moloney"]
MAKERS_SWITCH = ["Eaton (Cooper)", "ABB", "Siemens", "G&W", "S&C", "Schweitzer (SEL)"]


def density() -> float:
    return max(1.0, float(os.environ.get("OMS360_ASSET_DENSITY", "10")))


def score(a, customers: float, critical: bool, year: int | None = None) -> None:
    _score(a, customers, critical, year or utcnow().year)


def reference_date() -> str:
    """Ages are whole years from the install year to this date (install records carry the year only)."""
    return utcnow().date().isoformat()


# ---------------------------------------------------------------- sandbox register
def _point_on(route: list | None, rng: random.Random, lat: float, lng: float) -> tuple[float, float]:
    lines = [ln for ln in (route or []) if len(ln) >= 2]
    if not lines:
        return round(lat + rng.uniform(-0.03, 0.03), 5), round(lng + rng.uniform(-0.03, 0.03), 5)
    ln = rng.choice(lines)
    i = rng.randrange(len(ln) - 1)
    t = rng.random()
    return (round(ln[i][0] + t * (ln[i + 1][0] - ln[i][0]) + rng.uniform(-0.0006, 0.0006), 5),
            round(ln[i][1] + t * (ln[i + 1][1] - ln[i][1]) + rng.uniform(-0.0006, 0.0006), 5))


def _route_km(route: list | None) -> float:
    km = 0.0
    for ln in route or []:
        for a, b in zip(ln, ln[1:]):
            km += math.hypot((a[0] - b[0]) * 110.6, (a[1] - b[1]) * 111.3 * math.cos(math.radians(a[0])))
    return km


def _along(route: list | None, frac: float, lat: float, lng: float) -> tuple[float, float]:
    """The point a fraction of the way along a circuit's main line (reclosers sit mid-feeder)."""
    main = (route or [[]])[0]
    if len(main) < 2:
        return lat, lng
    p = main[min(len(main) - 1, max(0, round(frac * (len(main) - 1))))]
    return round(p[0], 5), round(p[1], 5)


def _gappy(rng: random.Random, a: Asset, no_year: float, no_insp: float) -> None:
    """A few sandbox records arrive with missing data, as real registers do."""
    if rng.random() < no_year:
        a.install_year = None
    if rng.random() < no_insp:
        a.inspection_score, a.last_inspection = None, None


def ensure_assets(s: Session) -> int:
    """Seed a synthetic asset register once per equipment type (new and existing databases). Older, tree-heavy circuits get
    older plant."""
    have = {k for (k,) in s.execute(select(Asset.kind).distinct()).all()}
    if have >= set(KINDS):
        return 0
    year = utcnow().year
    zones = {z.id: z for z in s.scalars(select(Zone)).all()}
    subs = s.scalars(select(Substation).order_by(Substation.id)).all()
    feeders = s.scalars(select(Feeder).order_by(Feeder.id)).all()
    crit = {f.feeder_id for f in s.scalars(select(Facility)).all()}
    sub_customers: dict[str, int] = {}
    for f in feeders:
        if f.substation_id:
            sub_customers[f.substation_id] = sub_customers.get(f.substation_id, 0) + f.customers
    sub_crit = {f.substation_id for f in feeders if f.id in crit}
    rows: list[dict] = []
    cols = [c.key for c in Asset.__table__.columns]

    def add(a: Asset, customers: float, critical: bool) -> None:
        a.details = a.details or {}
        a.source, a.status = "sandbox", "in_service"
        score(a, customers, critical, year)
        rows.append({c: getattr(a, c) for c in cols})

    if POWER not in have:
        for sub in subs:
            rng = random.Random(zlib.crc32(sub.id.encode()))
            n = rng.choice([1, 2, 2, 3])
            for k in range(n):
                age = int(rng.triangular(2, 64, 40))
                dga = max(60.0, rng.lognormvariate(math.log(120 + age * 14), 0.6))
                a = Asset(id=f"PT-{sub.id[4:]}-{k + 1}", kind=POWER, name=f"{sub.name} T{k + 1}", substation_id=sub.id, feeder_id=None,
                          zone_id=sub.zone_id, lat=round(sub.lat + 0.0004 * k, 5), lng=round(sub.lng + 0.0004 * k, 5), install_year=year - age,
                          manufacturer=rng.choice(MAKERS_POWER), rating_kva=float(rng.choice([20000, 28000, 33600, 50000])), mounting="sub", phases=3,
                          last_inspection=year - rng.randint(0, 2), inspection_score=max(1, min(5, round(1 + age / 30 + rng.gauss(0, 0.7)))),
                          peak_load_pct=round(rng.gauss(74, 14), 1), dga_tdcg_ppm=round(dga), oil_moisture_ppm=round(max(4, rng.gauss(6 + age * 0.35, 5)), 1),
                          through_faults=max(0, int(rng.gauss(age / 12, 2))), ltc=rng.random() < 0.7, maintenance_overdue=rng.random() < 0.12)
                if rng.random() < 0.06:
                    a.dga_tdcg_ppm = None  # oil test not on file
                add(a, sub_customers.get(sub.id, 0) / n, sub.id in sub_crit)

    per = density()
    for f in feeders:
        z = zones[f.zone_id]
        sub = next((x for x in subs if x.id == f.substation_id), None)
        rng = random.Random(zlib.crc32(f.id.encode()))
        vintage = 8 + 24 * rng.random() ** 0.9 * (0.6 + 0.6 * z.vulnerability) + max(0, year - f.last_trimmed)
        critical = f.id in crit
        if DIST not in have:
            n = max(4, round(f.customers / per))
            for i in range(n):
                renewed = rng.random() < 0.12  # replaced after a failure or upgrade
                age = rng.randint(0, 9) if renewed else int(max(0, min(66, rng.gauss(vintage, 9))))
                pole = rng.random() * 100 < f.overhead_pct
                three = rng.random() < 0.025
                kva = rng.choice([300.0, 500.0]) if three else rng.choice([25.0, 25.0, 37.5, 50.0]) if pole else rng.choice([50.0, 75.0, 75.0, 167.0])
                lat, lng = _point_on(f.route, rng, z.lat, z.lng)
                a = Asset(id=f"DT-{f.id[4:]}-{i + 1:04d}", kind=DIST, name=f"{'Pole' if pole else 'Pad'}-mount {kva:g} kVA", substation_id=f.substation_id,
                          feeder_id=f.id, zone_id=f.zone_id, lat=lat, lng=lng, install_year=year - age, manufacturer=rng.choice(MAKERS_DIST),
                          rating_kva=kva, mounting="pole" if pole else "pad", phases=3 if three else 1,
                          last_inspection=year - rng.randint(0, 6), inspection_score=max(1, min(5, round(1 + age / 22 + rng.gauss(0, 0.8)))),
                          peak_load_pct=round(max(20, rng.gauss(76, 17)), 1))
                _gappy(rng, a, 0.015, 0.04)
                add(a, f.customers / n, critical)
        frng = random.Random(zlib.crc32(("sw" + f.id).encode()))
        if BREAKER not in have and sub:
            age = int(max(1, min(60, frng.gauss(vintage + 4, 10))))
            intr = "oil" if age > 38 and frng.random() < 0.7 else frng.choice(["vacuum", "vacuum", "SF6"])
            rated = {"oil": 2000, "vacuum": 10000, "SF6": 5000}[intr]
            ty = year - frng.randint(0, 8)
            a = Asset(id=f"BK-{f.id[4:]}", kind=BREAKER, name=f"Feeder breaker {f.id}", substation_id=f.substation_id, feeder_id=f.id,
                      zone_id=f.zone_id, lat=round(sub.lat - 0.0003, 5), lng=round(sub.lng + 0.0003 * (int(f.id[-2:]) % 9), 5), install_year=year - age,
                      manufacturer=frng.choice(MAKERS_SWITCH), mounting="sub", phases=3, last_inspection=year - frng.randint(0, 3),
                      inspection_score=max(1, min(5, round(1 + age / 28 + frng.gauss(0, 0.7)))),
                      details={"interrupter": intr, "rated_operations": rated,
                               "operations": int(age * frng.uniform(15, 55) * (1 + f.overhead_pct / 100)),
                               "last_test_year": ty, "test_result": frng.choices(["pass", "marginal", "fail"], [80, 15, 5])[0]})
            if frng.random() < 0.05:
                a.details = {k: v for k, v in a.details.items() if k not in ("test_result", "last_test_year")}
            add(a, f.customers, critical)
        if RECLOSER not in have:
            for k in range(1 + (f.customers > 4000)):
                age = int(max(0, min(40, frng.gauss(vintage * 0.7, 7))))
                lat, lng = _along(f.route, 0.45 + 0.3 * k, z.lat, z.lng)
                a = Asset(id=f"RC-{f.id[4:]}-{k + 1}", kind=RECLOSER, name=f"Recloser {k + 1} on {f.id}", substation_id=f.substation_id,
                          feeder_id=f.id, zone_id=f.zone_id, lat=lat, lng=lng, install_year=year - age, manufacturer=frng.choice(MAKERS_SWITCH),
                          mounting="line", phases=3, last_inspection=year - frng.randint(0, 5),
                          inspection_score=max(1, min(5, round(1 + age / 20 + frng.gauss(0, 0.8)))),
                          details={"interrupter": "vacuum" if age < 25 else frng.choice(["oil", "vacuum"]), "rated_operations": 10000,
                                   "operations": int(age * frng.uniform(40, 160) * (0.5 + f.overhead_pct / 100)),
                                   "last_test_year": year - frng.randint(0, 9), "test_result": frng.choices(["pass", "marginal", "fail"], [78, 17, 5])[0]})
                add(a, f.customers * 0.5, critical)
        if POLE not in have and f.overhead_pct:
            n = max(3, round(_route_km(f.route) * 22 * f.overhead_pct / 100 * 10 / per))
            prng = random.Random(zlib.crc32(("pl" + f.id).encode()))
            for i in range(n):
                material = prng.choices(["wood", "steel", "concrete"], [92, 6, 2])[0]
                age = int(max(0, min(75, prng.gauss(vintage + 6, 12))))
                tested = prng.random() < 0.7
                strength = round(max(40.0, min(100.0, 100 - age * (0.55 if material == "wood" else 0.15) + prng.gauss(0, 6))), 0) if tested else None
                lat, lng = _point_on(f.route, prng, z.lat, z.lng)
                a = Asset(id=f"PL-{f.id[4:]}-{i + 1:04d}", kind=POLE, name=f"{material.title()} pole, class {prng.choice([2, 3, 4, 5])}",
                          substation_id=f.substation_id, feeder_id=f.id, zone_id=f.zone_id, lat=lat, lng=lng, install_year=year - age,
                          manufacturer="", mounting="line", phases=1, last_inspection=year - prng.randint(0, 10) if tested else None,
                          inspection_score=max(1, min(5, round(1 + age / 25 + prng.gauss(0, 0.8)))) if tested else None,
                          details={"material": material, "height_ft": prng.choice([35, 40, 40, 45, 50]),
                                   **({"strength_pct": strength, "strength_test_year": year - prng.randint(0, 10)} if tested else {})})
                if a.details.get("strength_test_year"):
                    a.last_inspection = a.details["strength_test_year"]
                _gappy(prng, a, 0.02, 0.0)
                add(a, f.customers / n * 6, critical)
    for i in range(0, len(rows), 5000):
        s.execute(insert(Asset), rows[i:i + 5000])
    s.commit()
    from .asset_history import seed_history
    seed_history(s)
    return len(rows)


def consequences(s: Session) -> dict[str, tuple[float, bool]]:
    """Customers who lose power when each unit fails, and whether a critical facility is behind it."""
    feeders = {f.id: f for f in s.scalars(select(Feeder)).all()}
    crit = {f.feeder_id for f in s.scalars(select(Facility)).all()}
    counts = {(k, fid): n for k, fid, n in s.execute(select(Asset.kind, Asset.feeder_id, func.count(Asset.id))
                                                     .where(Asset.feeder_id.is_not(None)).group_by(Asset.kind, Asset.feeder_id)).all()}
    sub_cust: dict[str, int] = {}
    for f in feeders.values():
        if f.substation_id:
            sub_cust[f.substation_id] = sub_cust.get(f.substation_id, 0) + f.customers
    sub_n = dict(s.execute(select(Asset.substation_id, func.count(Asset.id)).where(Asset.kind == POWER).group_by(Asset.substation_id)).all())
    sub_crit = {f.substation_id for f in feeders.values() if f.id in crit}
    out = {}
    for aid, kind, fid, sid in s.execute(select(Asset.id, Asset.kind, Asset.feeder_id, Asset.substation_id)).all():
        if kind == POWER:
            out[aid] = (sub_cust.get(sid, 0) / max(1, sub_n.get(sid, 1)), sid in sub_crit)
            continue
        f = feeders.get(fid)
        cust = f.customers if f else density()
        n = max(1, counts.get((kind, fid), 1))
        out[aid] = ({DIST: cust / n, BREAKER: cust, RECLOSER: cust * 0.5, POLE: cust / n * 6}.get(kind, cust / n), fid in crit)
    return out


def rescore(s: Session, ids: list[str] | None = None) -> int:
    """Recompute health and risk (after an import, a weight change, a replacement or a new year)."""
    year = utcnow().year
    cons = consequences(s)
    q = select(Asset) if ids is None else select(Asset).where(Asset.id.in_(ids))
    n = 0
    for a in s.scalars(q).all():
        c, crit = cons.get(a.id, (density(), False))
        score(a, c, crit, year)
        n += 1
    s.flush()
    _base_cache.clear()
    return n


def apply_weights(s: Session, weights: dict) -> dict:
    from ..db import set_setting
    import json
    w = validate_weights(weights)
    set_setting(s, SETTING_KEY, json.dumps(w))
    load_weights(json.dumps(w))
    rescore(s)
    return w


def init_model(s: Session) -> None:
    from ..db import get_setting
    load_weights(get_setting(s, SETTING_KEY, ""))


# ---------------------------------------------------------------- rollups
def _life_sql():
    return case((Asset.kind == POWER, 45), (Asset.kind == BREAKER, 40), (Asset.kind == RECLOSER, 30), (Asset.kind == POLE, 50),
                (Asset.mounting == "pad", 40), else_=35)


def _aggregates(year: int):
    age = year - Asset.install_year
    poor = case((Asset.condition.in_(POOR), 1), else_=0)
    over = case(((year - Asset.install_year) > _life_sql(), 1), else_=0)
    replace_cost = case((Asset.condition.in_(POOR), Asset.replacement_cost), else_=0)
    return (func.count(Asset.id), func.avg(age), func.max(age), func.avg(Asset.health_index), func.sum(poor), func.sum(over),
            func.sum(Asset.pof_12m), func.sum(Asset.risk_score), func.sum(replace_cost), func.sum(case((Asset.condition == "Critical", 1), else_=0)),
            func.sum(case((Asset.condition == "Unknown", 1), else_=0)), func.sum(case((Asset.status == "damaged", 1), else_=0)),
            func.count(Asset.install_year))


def _row(vals) -> dict:
    n, age, oldest, hi, poor, over, pof, risk, capex, critical, unknown, damaged, dated = vals
    n = n or 0
    return {"xfmrs": n, "units": n, "mean_age": round(age or 0, 1), "oldest": int(oldest or 0), "mean_hi": round(hi or 0, 1),
            "poor": int(poor or 0), "critical": int(critical or 0), "pct_poor": round((poor or 0) / n, 4) if n else 0,
            "pct_over_life": round((over or 0) / (dated or 1), 4) if n else 0, "expected_failures": round(pof or 0, 1),
            "risk": round(risk or 0, 1), "replacement_capex": round(capex or 0), "unknown": int(unknown or 0), "damaged": int(damaged or 0)}


def _scope(q, region: str | None = None, kind: str | None = None):
    if region:
        q = q.where(Asset.zone_id.in_(select(Zone.id).where(Zone.region_id == region)))
    if kind:
        q = q.where(Asset.kind == kind)
    return q


def circuit_factors(s: Session) -> dict[str, dict]:
    """Per circuit, what the storm prediction needs: mean transformer health, Poor/Critical share, mean age, transformer count."""
    year = utcnow().year
    rows = s.execute(select(Asset.feeder_id, func.avg(Asset.health_index), func.avg(case((Asset.condition.in_(POOR), 1.0), else_=0.0)),
                            func.avg(year - Asset.install_year), func.count(Asset.id))
                     .where(Asset.kind == DIST, Asset.feeder_id.is_not(None)).group_by(Asset.feeder_id)).all()
    return {fid: {"hi": hi if hi is not None else 70.0, "poor": poor, "age": age or 0.0, "xfmrs": n} for fid, hi, poor, age, n in rows}


def circuit_health(s: Session, region: str | None = None, zone: str | None = None, substation: str | None = None) -> list[dict]:
    from .ops import network_index
    year = utcnow().year
    idx = network_index(s)
    rows = s.execute(select(Asset.feeder_id, *_aggregates(year)).where(Asset.kind == DIST).group_by(Asset.feeder_id)).all()
    other = {(k, fid): _row(v) for k, fid, *v in s.execute(select(Asset.kind, Asset.feeder_id, *_aggregates(year))
                                                           .where(Asset.kind.in_((POLE, BREAKER, RECLOSER))).group_by(Asset.kind, Asset.feeder_id)).all()}
    feeders = {f.id: f for f in s.scalars(select(Feeder)).all()}
    crit = {f.feeder_id: f.name for f in s.scalars(select(Facility)).all()}
    out = []
    for fid, *vals in rows:
        info, f = idx.get(fid, {}), feeders.get(fid)
        if region and info.get("region_id") != region or zone and info.get("zone_id") != zone or substation and info.get("substation_id") != substation:
            continue
        pl, sw = other.get((POLE, fid)), [other.get((BREAKER, fid)), other.get((RECLOSER, fid))]
        sw = [x for x in sw if x]
        out.append({"id": fid, "zone_id": info.get("zone_id"), "zone": info.get("zone"), "region_id": info.get("region_id"),
                    "region": info.get("region"), "substation_id": info.get("substation_id"), "substation": info.get("substation"),
                    "customers": f.customers if f else 0, "overhead_pct": f.overhead_pct if f else None,
                    "critical_facility": crit.get(fid), **_row(vals),
                    "poles": pl["units"] if pl else 0, "poles_poor": pl["poor"] if pl else 0,
                    "switchgear": sum(x["units"] for x in sw), "switchgear_poor": sum(x["poor"] for x in sw),
                    "risk_all": round(sum(x["risk"] for x in [_row(vals), *(sw or []), *([pl] if pl else [])]), 1)})
    out.sort(key=lambda r: -r["risk"])
    return out


def region_health(s: Session, kind: str = DIST) -> list[dict]:
    year = utcnow().year
    regions = {r.id: r.name for r in s.scalars(select(Region)).all()}
    out = []
    for rid, *vals in s.execute(select(Zone.region_id, *_aggregates(year)).select_from(Asset).join(Zone, Zone.id == Asset.zone_id)
                                .where(Asset.kind == kind).group_by(Zone.region_id)).all():
        r = _row(vals)
        circuits = s.scalar(select(func.count(Feeder.id)).join(Zone, Zone.id == Feeder.zone_id).where(Zone.region_id == rid))
        substations_n = s.scalar(select(func.count(Substation.id)).join(Zone, Zone.id == Substation.zone_id).where(Zone.region_id == rid))
        p = _row(s.execute(select(*_aggregates(year)).select_from(Asset).join(Zone, Zone.id == Asset.zone_id)
                           .where(Asset.kind == POWER, Zone.region_id == rid)).one())
        allk = _row(s.execute(select(*_aggregates(year)).select_from(Asset).join(Zone, Zone.id == Asset.zone_id).where(Zone.region_id == rid)).one())
        out.append({"id": rid, "name": regions.get(rid, "Unassigned"), "circuits": circuits, "substations": substations_n, **r,
                    "power_transformers": p["xfmrs"], "power_poor": p["poor"], "power_mean_age": p["mean_age"],
                    "replacement_capex": allk["replacement_capex"], "all_units": allk["units"], "all_poor": allk["poor"],
                    "all_damaged": allk["damaged"], "all_risk": allk["risk"]})
    out.sort(key=lambda r: r["name"])
    return out


def summary(s: Session, region: str | None = None) -> dict:
    """Fleet KPIs (one region when given): distribution transformers, substation units, every type, condition bands and age."""
    year = utcnow().year
    agg = lambda kind: _row(s.execute(_scope(select(*_aggregates(year)), region, kind)).one())  # noqa: E731
    bands = lambda kind: dict(s.execute(_scope(select(Asset.condition, func.count(Asset.id)), region, kind).group_by(Asset.condition)).all())  # noqa: E731
    d, p = agg(DIST), agg(POWER)
    by_kind = []
    for k, label in KINDS.items():
        r = agg(k)
        if r["units"]:
            by_kind.append({"kind": k, "label": label, **r, "bands": {b: bands(k).get(b, 0) for b in CONDITIONS}})
    total = agg(None)
    decades = [{"decade": "Not recorded" if k is None else f"{int(k) * 10}–{int(k) * 10 + 9} y", "count": n}
               for k, n in s.execute(_scope(select(((year - Asset.install_year) // 10).label("d"), func.count(Asset.id)), region, DIST)
                                     .group_by("d").order_by("d")).all()]
    regions = region_health(s)
    return {"region": region, "distribution": d, "power": p, "all": total, "by_kind": by_kind,
            "bands": {b: bands(DIST).get(b, 0) for b in CONDITIONS}, "power_bands": {b: bands(POWER).get(b, 0) for b in CONDITIONS},
            "age_histogram": decades, "regions": regions if not region else [r for r in regions if r["id"] == region],
            "replacement_capex": total["replacement_capex"], "density": density(), "reference_date": reference_date(),
            "sources": dict(s.execute(_scope(select(Asset.source, func.count(Asset.id)), region).group_by(Asset.source)).all()),
            "open_work_orders": s.scalar(select(func.count(WorkOrder.id)).where(WorkOrder.status.in_(("open", "scheduled"))))}


def serial(a: Asset, year: int | None = None) -> dict:
    year = year or utcnow().year
    age = year - a.install_year if a.install_year is not None and a.install_year <= year else None
    return {"id": a.id, "kind": a.kind, "kind_label": KINDS.get(a.kind, a.kind), "name": a.name, "substation_id": a.substation_id,
            "feeder_id": a.feeder_id, "zone_id": a.zone_id, "lat": a.lat, "lng": a.lng, "install_year": a.install_year, "age": age,
            "age_reference": reference_date(), "manufacturer": a.manufacturer, "rating_kva": a.rating_kva, "mounting": a.mounting,
            "phases": a.phases, "last_inspection": a.last_inspection, "inspection_score": a.inspection_score, "peak_load_pct": a.peak_load_pct,
            "dga_tdcg_ppm": a.dga_tdcg_ppm, "oil_moisture_ppm": a.oil_moisture_ppm, "through_faults": a.through_faults, "ltc": a.ltc,
            "maintenance_overdue": a.maintenance_overdue, "details": a.details or {}, "source": a.source, "status": a.status,
            "health_index": a.health_index, "condition": a.condition, "pof_12m": a.pof_12m, "risk_score": a.risk_score,
            "replacement_cost": a.replacement_cost, "drivers": a.drivers or [], "gaps": a.gaps or [], "confidence": a.confidence}


def circuit_detail(s: Session, feeder_id: str, limit: int = 50, offset: int = 0, sort: str = "risk", kind: str = DIST) -> dict | None:
    year = utcnow().year
    rows = [r for r in circuit_health(s) if r["id"] == feeder_id]
    if not rows:
        return None
    c = rows[0]
    order = {"risk": Asset.risk_score.desc(), "age": Asset.install_year.asc(), "health": Asset.health_index.asc()}.get(sort, Asset.risk_score.desc())
    kind = kind if kind in KINDS and kind != POWER else DIST
    q = select(Asset).where(Asset.kind == kind, Asset.feeder_id == feeder_id)
    units = s.scalars(q.order_by(Asset.health_index.is_(None), order).offset(offset).limit(limit)).all()
    kind_total = s.scalar(select(func.count(Asset.id)).where(Asset.kind == kind, Asset.feeder_id == feeder_id))
    decades = s.execute(select(((year - Asset.install_year) // 10).label("d"), func.count(Asset.id))
                        .where(Asset.kind == DIST, Asset.feeder_id == feeder_id).group_by("d").order_by("d")).all()
    hi_bins = s.execute(select(cast(func.min(Asset.health_index, 99.9) / 10, Integer).label("b"), func.count(Asset.id))
                        .where(Asset.kind == DIST, Asset.feeder_id == feeder_id).group_by("b").order_by("b")).all()
    bands = dict(s.execute(select(Asset.condition, func.count(Asset.id)).where(Asset.kind == DIST, Asset.feeder_id == feeder_id)
                           .group_by(Asset.condition)).all())
    kinds = {k: _row(v) for k, *v in s.execute(select(Asset.kind, *_aggregates(year)).where(Asset.feeder_id == feeder_id).group_by(Asset.kind)).all()}
    power = s.scalars(select(Asset).where(Asset.kind == POWER, Asset.substation_id == c["substation_id"]).order_by(Asset.id)).all() \
        if c["substation_id"] else []
    f = s.get(Feeder, feeder_id)
    return {**c, "route": f.route if f else None, "route_source": f.route_source if f else None, "bands": {b: bands.get(b, 0) for b in CONDITIONS},
            "age_histogram": [{"decade": "Not recorded" if k is None else f"{int(k) * 10}–{int(k) * 10 + 9} y", "count": n} for k, n in decades],
            "hi_histogram": [{"band": f"{int(k) * 10}–{int(k) * 10 + 10}", "count": n} for k, n in hi_bins if k is not None],
            "kinds": [{"kind": k, "label": KINDS[k], **kinds[k]} for k in KINDS if k in kinds],
            "list_kind": kind, "list_total": kind_total, "transformers": [serial(a, year) for a in units], "offset": offset, "limit": limit,
            "power_transformers": [serial(a, year) for a in power]}


def circuit_markers(s: Session, feeder_id: str) -> list[dict]:
    """Every unit on a circuit (and its substation's units) for the map: position, type, condition and confirmed status."""
    f = s.get(Feeder, feeder_id)
    if not f:
        return []
    q = select(Asset.id, Asset.kind, Asset.name, Asset.lat, Asset.lng, Asset.condition, Asset.health_index, Asset.status).where(
        (Asset.feeder_id == feeder_id) | ((Asset.kind == POWER) & (Asset.substation_id == f.substation_id)))
    return [{"id": i, "kind": k, "name": n, "lat": la, "lng": ln, "condition": c, "health_index": h, "status": st}
            for i, k, n, la, ln, c, h, st in s.execute(q).all()]


def substations(s: Session, region: str | None = None) -> list[dict]:
    from .ops import network_index
    idx = network_index(s)
    sub_region = {v["substation_id"]: (v["region_id"], v["region"], v["zone"]) for v in idx.values() if v["substation_id"]}
    subs = {x.id: x for x in s.scalars(select(Substation)).all()}
    year = utcnow().year
    out = []
    for a in s.scalars(select(Asset).where(Asset.kind == POWER).order_by(Asset.risk_score.desc())).all():
        rid, rname, zname = sub_region.get(a.substation_id, (None, None, None))
        if region and rid != region:
            continue
        sub = subs.get(a.substation_id)
        out.append(serial(a, year) | {"substation": sub.name if sub else a.substation_id, "region_id": rid, "region": rname, "zone": zname,
                                      "circuits": sum(1 for v in idx.values() if v["substation_id"] == a.substation_id)})
    return out


def substation_rollup(s: Session, region: str | None = None) -> list[dict]:
    """One row per substation: its circuits, its power transformers' and breakers' worst condition, and fleet health below it."""
    from .ops import network_index
    year = utcnow().year
    idx = network_index(s)
    subs = s.scalars(select(Substation).order_by(Substation.id)).all()
    zones = {z.id: z for z in s.scalars(select(Zone)).all()}
    regions = {r.id: r.name for r in s.scalars(select(Region)).all()}
    units = {(sid, k): _row(v) for sid, k, *v in s.execute(select(Asset.substation_id, Asset.kind, *_aggregates(year))
                                                           .group_by(Asset.substation_id, Asset.kind)).all()}
    worst = dict(s.execute(select(Asset.substation_id, func.min(Asset.health_index)).where(Asset.kind.in_((POWER, BREAKER)))
                           .group_by(Asset.substation_id)).all())
    out = []
    for sub in subs:
        rid = zones[sub.zone_id].region_id if sub.zone_id in zones else None
        if region and rid != region:
            continue
        cs = [fid for fid, v in idx.items() if v["substation_id"] == sub.id]
        d, pw, bk = units.get((sub.id, DIST)), units.get((sub.id, POWER)), units.get((sub.id, BREAKER))
        out.append({"id": sub.id, "name": sub.name, "zone_id": sub.zone_id, "zone": zones[sub.zone_id].short if sub.zone_id in zones else None,
                    "region_id": rid, "region": regions.get(rid), "lat": sub.lat, "lng": sub.lng, "circuits": len(cs),
                    "customers": sum(idx[c]["customers"] or 0 for c in cs),
                    "power_transformers": pw["units"] if pw else 0, "power_poor": pw["poor"] if pw else 0,
                    "breakers": bk["units"] if bk else 0, "breakers_poor": bk["poor"] if bk else 0,
                    "worst_hi": worst.get(sub.id), "dist_mean_hi": d["mean_hi"] if d else None, "dist_poor": d["poor"] if d else 0,
                    "risk": round(sum(x["risk"] for (sid, _), x in units.items() if sid == sub.id), 1)})
    out.sort(key=lambda r: -r["risk"])
    return out


def top_risk(s: Session, n: int = 10, region: str | None = None, kind: str | None = None) -> list[dict]:
    year = utcnow().year
    return [serial(a, year) for a in s.scalars(_scope(select(Asset), region, kind).order_by(Asset.risk_score.desc()).limit(n)).all()]


def search(s: Session, q: str, limit: int = 20) -> list[dict]:
    like = f"%{q.strip()}%"
    year = utcnow().year
    return [serial(a, year) for a in s.scalars(select(Asset).where(Asset.id.ilike(like) | Asset.name.ilike(like)).order_by(Asset.id).limit(limit)).all()]


# ---------------------------------------------------------------- import
FIELDS = ("id", "kind", "name", "substation_id", "feeder_id", "lat", "lng", "install_year", "manufacturer", "rating_kva", "mounting",
          "phases", "last_inspection", "inspection_score", "peak_load_pct", "dga_tdcg_ppm", "oil_moisture_ppm", "through_faults", "ltc",
          "maintenance_overdue", "material", "height_ft", "strength_pct", "strength_test_year", "interrupter", "operations",
          "rated_operations", "last_test_year", "test_result")
SAMPLE_CSV = ("id,kind,feeder_id,substation_id,install_year,rating_kva,mounting,inspection_score,last_inspection,peak_load_pct,dga_tdcg_ppm,"
              "material,strength_pct,strength_test_year,operations,test_result,last_test_year\n"
              "DT-NEW-0001,dist_transformer,{feeder},,1978,50,pole,4,2023,112,,,,,,,\n"
              "DT-NEW-0002,dist_transformer,{feeder},,,25,pole,,,,,,,,,,\n"
              "PT-NEW-1,power_transformer,,{sub},1969,28000,sub,3,2025,96,2400,,,,,,\n"
              "PL-NEW-0001,pole,{feeder},,1971,0,line,3,2022,,,wood,63,2022,,,\n"
              "RC-NEW-1,recloser,{feeder},,1999,0,line,2,2024,,,,,,8800,marginal,2021\n")
DETAIL_FIELDS = {POLE: ("material", "height_ft", "strength_pct", "strength_test_year"),
                 BREAKER: ("interrupter", "operations", "rated_operations", "last_test_year", "test_result"),
                 RECLOSER: ("interrupter", "operations", "rated_operations", "last_test_year", "test_result")}


class AssetImportError(ValueError):
    pass


def _num(v, cast=float):
    if v in (None, ""):
        return None
    try:
        return cast(float(v)) if cast is int else cast(v)
    except (TypeError, ValueError):
        raise AssetImportError(f"'{v}' is not a number")


def import_csv(s: Session, text: str, replace: bool = False) -> dict:
    """Load the utility's asset register: one row per unit, matched by id (update) or added. A blank install_year or
    inspection is kept blank (shown as unknown); impossible values are rejected. replace=True clears the sandbox register first."""
    reader = csv.DictReader(io.StringIO(text.strip()))
    if not reader.fieldnames or "id" not in [f.strip().lower() for f in reader.fieldnames]:
        raise AssetImportError("CSV needs a header row with at least: id, kind, feeder_id or substation_id")
    feeders = {f.id: f for f in s.scalars(select(Feeder)).all()}
    subs = {x.id: x for x in s.scalars(select(Substation)).all()}
    zones = {z.id: z for z in s.scalars(select(Zone)).all()}
    year = utcnow().year
    rows = []
    for i, raw in enumerate(reader, 2):
        r = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        try:
            kind = r.get("kind") or (POWER if r.get("substation_id") and not r.get("feeder_id") else DIST)
            if kind not in KINDS:
                raise AssetImportError(f"kind must be one of {', '.join(KINDS)}")
            if not r.get("id"):
                raise AssetImportError("id is required")
            fid, sid = r.get("feeder_id") or None, r.get("substation_id") or None
            if kind != POWER and fid not in feeders:
                raise AssetImportError(f"unknown feeder_id '{fid}'")
            if kind == POWER and sid not in subs:
                raise AssetImportError(f"unknown substation_id '{sid}'")
            yr = _num(r.get("install_year"), int)
            if yr is not None and not 1900 <= yr <= year:
                raise AssetImportError(f"install_year must be between 1900 and {year} (leave it blank if unknown)")
            last = _num(r.get("last_inspection"), int)
            if last is not None and (not 1900 <= last <= year or yr is not None and last < yr):
                raise AssetImportError(f"last_inspection must be between the install year and {year}")
            sid = sid or (feeders[fid].substation_id if fid else None)
            home = feeders[fid] if fid else None
            zid = home.zone_id if home else subs[sid].zone_id
            lat, lng = _num(r.get("lat")), _num(r.get("lng"))
            if lat is None or lng is None:
                lat, lng = (subs[sid].lat, subs[sid].lng) if kind == POWER else _point_on(home.route, random.Random(r["id"]), zones[zid].lat, zones[zid].lng)
            score_ = _num(r.get("inspection_score"), int)
            if score_ is not None and not 1 <= score_ <= 5:
                raise AssetImportError("inspection_score must be 1–5")
            details = {}
            for k in DETAIL_FIELDS.get(kind, ()):
                v = r.get(k, "")
                if v == "":
                    continue
                if k in ("material", "interrupter", "test_result"):
                    details[k] = v.lower()
                else:
                    details[k] = _num(v, int if k != "strength_pct" else float)
            if details.get("test_result") and details["test_result"] not in ("pass", "marginal", "fail"):
                raise AssetImportError("test_result must be pass, marginal or fail")
            if details.get("strength_pct") is not None and not 0 <= details["strength_pct"] <= 100:
                raise AssetImportError("strength_pct must be 0–100")
            rows.append({"id": r["id"][:24], "kind": kind, "name": r.get("name") or KINDS[kind], "substation_id": sid,
                         "feeder_id": fid if kind != POWER else None, "zone_id": zid, "lat": lat, "lng": lng, "install_year": yr,
                         "manufacturer": r.get("manufacturer", "")[:40],
                         "rating_kva": _num(r.get("rating_kva")) or (28000.0 if kind == POWER else 50.0 if kind == DIST else 0.0),
                         "mounting": r.get("mounting") or {POWER: "sub", BREAKER: "sub", DIST: "pole"}.get(kind, "line"),
                         "phases": _num(r.get("phases"), int) or (3 if kind in (POWER, BREAKER, RECLOSER) else 1),
                         "last_inspection": last, "inspection_score": score_,
                         "peak_load_pct": _num(r.get("peak_load_pct")), "dga_tdcg_ppm": _num(r.get("dga_tdcg_ppm")),
                         "oil_moisture_ppm": _num(r.get("oil_moisture_ppm")), "through_faults": _num(r.get("through_faults"), int),
                         "ltc": r.get("ltc", "").lower() in ("1", "true", "yes", "y"),
                         "maintenance_overdue": r.get("maintenance_overdue", "").lower() in ("1", "true", "yes", "y"),
                         "details": details, "source": "imported"})
        except AssetImportError as ex:
            raise AssetImportError(f"Row {i}: {ex}")
    if not rows:
        raise AssetImportError("The file has no asset rows.")
    if replace:
        s.execute(delete(AssetEvent))
        s.execute(delete(WorkOrder))
        s.execute(delete(Asset))
    added = updated = 0
    for r in rows:
        a = s.get(Asset, r["id"])
        if a:
            updated += 1
        else:
            a = Asset(id=r["id"], status="in_service")
            s.add(a)
            added += 1
        for k, v in r.items():
            setattr(a, k, v)
    s.flush()
    rescore(s, None if replace else [r["id"] for r in rows])
    return {"added": added, "updated": updated, "total": s.scalar(select(func.count(Asset.id))),
            "missing_install_year": sum(1 for r in rows if r["install_year"] is None)}


# ---------------------------------------------------------------- replacement planning
HORIZONS = (0, 5, 10)
_base_cache: dict[tuple, dict] = {}
_new_cache: dict[tuple, tuple] = {}
PLAN_COLS = ("id", "kind", "name", "install_year", "mounting", "inspection_score", "last_inspection", "peak_load_pct", "dga_tdcg_ppm",
             "oil_moisture_ppm", "through_faults", "ltc", "maintenance_overdue", "rating_kva", "health_index", "condition", "pof_12m",
             "risk_score", "replacement_cost", "feeder_id", "substation_id", "zone_id", "drivers", "details", "status")


def _fingerprint(s: Session) -> tuple:
    n, hi, cost = s.execute(select(func.count(Asset.id), func.sum(Asset.health_index), func.sum(Asset.replacement_cost))).one()
    from .asset_model import WEIGHTS
    return (str(s.get_bind().url), n, round(hi or 0, 1), round(cost or 0), utcnow().year, tuple(sorted(WEIGHTS.items())))


def _new_unit(unit) -> dict:
    d = dict(unit.details or {})
    if unit.kind == POLE:
        d |= {"strength_pct": 100.0, "strength_test_year": utcnow().year}
    if unit.kind in SWITCHGEAR:
        d |= {"operations": 0, "test_result": "pass", "last_test_year": utcnow().year, "interrupter": "vacuum"}
    return {"install_year": utcnow().year, "inspection_score": 1, "last_inspection": utcnow().year, "through_faults": 0,
            "maintenance_overdue": False, "dga_tdcg_ppm": 150.0 if unit.kind == POWER else None,
            "oil_moisture_ppm": 8.0 if unit.kind == POWER else None, "details": d}


def _project(unit, cons: float, year: int, replaced: bool) -> tuple[float, bool, float]:
    """(pof, poor?, risk) for one unit in `year`: as it ages untouched, or replaced with a new unit this year."""
    from types import SimpleNamespace
    if replaced:  # a new unit's outlook depends only on its type, loading and tap changer: share the result
        key = (unit.kind, unit.mounting, unit.ltc, round(unit.peak_load_pct or 0), (unit.details or {}).get("material"), year)
        hit = _new_cache.get(key)
        if hit is None:
            a = SimpleNamespace(**{**vars(unit), **_new_unit(unit)})
            score(a, 1.0, False, year)
            hit = _new_cache[key] = (a.pof_12m, a.condition in POOR)
        return hit[0], hit[1], hit[0] * cons
    if year == utcnow().year:
        return unit.pof_12m, unit.condition in POOR, unit.pof_12m * cons
    a = SimpleNamespace(**vars(unit))
    score(a, 1.0, False, year)
    return a.pof_12m, a.condition in POOR, a.pof_12m * cons


def _base(s: Session) -> dict:
    """The whole fleet and its outlook now, in 5 and in 10 years, with and without replacement. Computed once per register
    state (a few seconds on ~120k units; warmed at startup) and filtered by region or kind for each plan."""
    from types import SimpleNamespace
    key = _fingerprint(s)
    base = _base_cache.get(key)
    if base is not None:
        return base
    year = utcnow().year
    fleet = []
    for row in s.execute(select(*(getattr(Asset, c) for c in PLAN_COLS), Zone.region_id).join(Zone, Zone.id == Asset.zone_id)).all():
        a = SimpleNamespace(**dict(zip(PLAN_COLS, row[:-1])))
        fleet.append({"a": a, "region_id": row[-1], "cons": a.risk_score / a.pof_12m if a.pof_12m else 0.0})
    base = {"fleet": fleet,
            "rows": [[_project(f["a"], f["cons"], year + h, False) for h in HORIZONS] for f in fleet],
            "new": [[_project(f["a"], f["cons"], year + h, True) for h in HORIZONS] for f in fleet]}
    _base_cache.clear()
    _base_cache[key] = base
    return base


def warm_plan_cache() -> None:
    """Background warm-up so the first replacement plan answers instantly."""
    from ..db import SessionLocal
    with SessionLocal() as s:
        init_model(s)
        _base(s)


def replacement_plan(s: Session, budget: float, region: str | None = None, kind: str | None = None, items: int = 150) -> dict:
    """Which units to replace for a budget: ranked by risk removed per dollar (customer-outages a year avoided, averaged over
    now, +5 and +10 years so ageing counts), taken greedily until the budget is spent. Also the fleet's condition now and in
    5 and 10 years, with no action and with the plan. A replaced unit is new; the rest keep ageing with today's inspection
    and test results (a conservative no-action case). Units with an unknown install year are planned on an estimate."""
    year = utcnow().year
    full = _base(s)
    keep = [i for i, f in enumerate(full["fleet"]) if (not region or f["region_id"] == region) and (not kind or f["a"].kind == kind)]
    fleet = [full["fleet"][i] for i in keep]
    base = {"rows": [full["rows"][i] for i in keep], "new": [full["new"][i] for i in keep]}
    if not fleet:
        return {"budget": budget, "region": region, "kind": kind, "units": 0, "cost": 0, "by_kind": {}, "poor_replaced": 0, "fleet": 0,
                "risk_reduced_pct": 0, "failures_avoided": 0, "projection": [], "frontier": [], "by_region": [], "items": []}
    n_h = len(HORIZONS)
    cand = []
    for i, f in enumerate(fleet):
        removed = sum(base["rows"][i][k][2] - base["new"][i][k][2] for k in range(n_h)) / n_h
        if removed > 0 and f["a"].replacement_cost > 0:
            cand.append((removed / f["a"].replacement_cost, removed, i))
    cand.sort(reverse=True)
    total = sum(base["rows"][i][k][2] for i in range(len(fleet)) for k in range(n_h)) / n_h or 1.0
    chosen, spent, cum_cost, cum_removed, frontier = [], 0.0, 0.0, 0.0, []
    marks = [b * 1e6 for b in (1, 2, 5, 10, 20, 35, 50, 75, 100, 150, 200, 300)]
    for _, removed, i in cand:
        cost = fleet[i]["a"].replacement_cost
        if spent + cost <= budget:
            chosen.append(i)
            spent += cost
        cum_cost += cost
        cum_removed += removed
        while marks and cum_cost >= marks[0]:
            frontier.append({"budget": marks.pop(0), "risk_reduced_pct": round(cum_removed / total, 4)})
    pick = set(chosen)

    def at(k: int, plan: bool) -> dict:
        rows = [base["new"][i][k] if plan and i in pick else base["rows"][i][k] for i in range(len(fleet))]
        return {"pct_poor": round(sum(1 for r in rows if r[1]) / len(rows), 4), "poor": sum(1 for r in rows if r[1]),
                "expected_failures": round(sum(r[0] for r in rows), 1), "risk": round(sum(r[2] for r in rows), 1)}

    projection = [{"year": year + h, "label": "Now" if h == 0 else f"+{h} y", "no_action": at(k, False), "with_plan": at(k, True)}
                  for k, h in enumerate(HORIZONS)]
    regions = {r.id: r.name for r in s.scalars(select(Region)).all()}
    gain = {i: base["rows"][i][0][2] - base["new"][i][0][2] for i in chosen}
    by_region: dict[str, dict] = {}
    for i in chosen:
        f = fleet[i]
        r = by_region.setdefault(f["region_id"], {"id": f["region_id"], "name": regions.get(f["region_id"], "Unassigned"), "units": 0, "power": 0,
                                                  "cost": 0.0, "risk_reduced": 0.0})
        r["units"] += 1
        r["power"] += f["a"].kind == POWER
        r["cost"] += f["a"].replacement_cost
        r["risk_reduced"] += gain[i]
    now_risk = projection[0]["no_action"]["risk"] or 1.0
    return {
        "budget": budget, "region": region, "kind": kind, "units": len(chosen), "cost": round(spent), "fleet": len(fleet),
        "by_kind": {k: sum(1 for i in chosen if fleet[i]["a"].kind == k) for k in KINDS},
        "poor_replaced": sum(1 for i in chosen if fleet[i]["a"].condition in POOR),
        "risk_reduced_pct": round(1 - projection[0]["with_plan"]["risk"] / now_risk, 4),
        "failures_avoided": round(projection[0]["no_action"]["expected_failures"] - projection[0]["with_plan"]["expected_failures"], 1),
        "projection": projection, "frontier": frontier,
        "by_region": sorted(({**r, "cost": round(r["cost"]), "risk_reduced": round(r["risk_reduced"], 1)} for r in by_region.values()),
                            key=lambda r: -r["risk_reduced"]),
        "items": [{"id": fleet[i]["a"].id, "kind": fleet[i]["a"].kind, "name": fleet[i]["a"].name,
                   "where": fleet[i]["a"].feeder_id or fleet[i]["a"].substation_id, "region": regions.get(fleet[i]["region_id"]),
                   "age": year - fleet[i]["a"].install_year if fleet[i]["a"].install_year else None,
                   "health_index": fleet[i]["a"].health_index, "condition": fleet[i]["a"].condition,
                   "cost": fleet[i]["a"].replacement_cost, "risk_reduced": round(gain[i], 2), "drivers": (fleet[i]["a"].drivers or [])[:2]}
                  for i in sorted(chosen, key=lambda i: -gain[i])[:items]],
    }
