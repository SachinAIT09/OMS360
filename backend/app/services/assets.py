"""Asset age and health for major equipment: substation power transformers and distribution transformers.

A health index (HI, 0 end of life … 100 as new) is built from explainable penalties, CNAIM-style but simpler:
  age            45 × min(1.5, age / design life)^2.2 — design life 45 y power, 35 y pole-mount, 40 y pad-mount
  condition      inspection score 1–5 → 0 / 4 / 10 / 22 / 35
  loading        0.6 per % of peak load above nameplate (max 20)
  power only     dissolved gas (IEEE C57.104 TDCG condition 1–4 → 0 / 10 / 22 / 35), oil moisture (> 25 ppm 6, > 35 ppm 12),
                 through-faults (1.5 each, max 15), maintenance overdue 6, on-load tap changer older than 30 y 4
  condition band Good ≥ 70, Fair ≥ 50, Poor ≥ 30, Critical below

Probability of failure in the next 12 months is Weibull (β 3.5; η 70 y power / 60 y distribution) on an effective age:
the asset's age plus its non-age penalties converted to years (a 45-point penalty ≈ one design life). Risk = PoF ×
customers who lose power when it fails (× 2 when a critical facility is on the circuit), so the replacement list is
ranked by expected customer impact, not just by age.

The sandbox seeds a synthetic register (deterministic per circuit and substation) until the utility imports its own
(Admin → Assets, CSV). Density: OMS360_ASSET_DENSITY customers per distribution transformer (default 10).
"""
import csv
import io
import math
import os
import random

from sqlalchemy import Integer, case, cast, delete, func, insert, select
from sqlalchemy.orm import Session

from ..models import Asset, Facility, Feeder, Region, Substation, Zone, utcnow

POWER, DIST = "power_transformer", "dist_transformer"
KINDS = {POWER: "Substation power transformer", DIST: "Distribution transformer"}
BANDS = (("Good", 70), ("Fair", 50), ("Poor", 30), ("Critical", 0))
POOR = ("Poor", "Critical")
INSPECTION = {1: 0, 2: 4, 3: 10, 4: 22, 5: 35}
WEIBULL = {POWER: (70.0, 3.5), DIST: (60.0, 3.5)}
MAKERS_POWER = ["GE", "Westinghouse", "ABB", "Siemens", "Hitachi Energy", "SPX Waukesha", "Virginia Transformer", "Howard"]
MAKERS_DIST = ["Howard", "ERMCO", "Eaton", "GE", "Westinghouse", "ABB", "Central Moloney"]


def density() -> float:
    return max(1.0, float(os.environ.get("OMS360_ASSET_DENSITY", "10")))


def life(a: Asset) -> float:
    return 45.0 if a.kind == POWER else 40.0 if a.mounting == "pad" else 35.0


def _dga_condition(ppm: float | None) -> int:
    if ppm is None:
        return 1
    return 1 if ppm <= 720 else 2 if ppm <= 1920 else 3 if ppm <= 4630 else 4


def score(a: Asset, customers: float, critical: bool, year: int | None = None) -> None:
    """Fill the computed fields: health index, condition, drivers, 12-month PoF, risk and replacement cost."""
    year = year or utcnow().year
    age = max(0, year - a.install_year)
    L = life(a)
    pen: list[tuple[float, str]] = [(45 * min(1.5, age / L) ** 2.2, f"Age {age} y of {L:.0f} y design life")]
    if a.inspection_score:
        pen.append((INSPECTION.get(a.inspection_score, 0), f"Inspection score {a.inspection_score}/5" + (f" ({a.last_inspection})" if a.last_inspection else "")))
    if a.peak_load_pct and a.peak_load_pct > 100:
        pen.append((min(20, 0.6 * (a.peak_load_pct - 100)), f"Peak load {a.peak_load_pct:.0f}% of nameplate"))
    if a.kind == POWER:
        c = _dga_condition(a.dga_tdcg_ppm)
        pen.append(({1: 0, 2: 10, 3: 22, 4: 35}[c], f"Dissolved gas {a.dga_tdcg_ppm:,.0f} ppm TDCG (condition {c})" if a.dga_tdcg_ppm else "No DGA on file"))
        m = a.oil_moisture_ppm or 0
        pen.append((12 if m > 35 else 6 if m > 25 else 0, f"Oil moisture {m:.0f} ppm"))
        pen.append((min(15, 1.5 * (a.through_faults or 0)), f"{a.through_faults or 0} through-faults"))
        pen.append((6 if a.maintenance_overdue else 0, "Maintenance overdue"))
        pen.append((4 if a.ltc and age > 30 else 0, "Tap changer over 30 y"))
    total = sum(p for p, _ in pen)
    a.health_index = round(max(0.0, min(100.0, 100 - total)), 1)
    a.condition = next(b for b, lo in BANDS if a.health_index >= lo)
    a.drivers = [t for p, t in sorted(pen, key=lambda x: -x[0]) if p >= 3][:4]
    eff = age + (total - pen[0][0]) / 45 * L  # condition penalties as extra years
    eta, beta = WEIBULL[a.kind]
    a.pof_12m = round(1 - math.exp(-(((eff + 1) / eta) ** beta - (eff / eta) ** beta)), 5)
    a.risk_score = round(a.pof_12m * customers * (2 if critical else 1), 4)
    if a.kind == POWER:
        a.replacement_cost = round(a.rating_kva / 1000 * 85000 + (250000 if a.ltc else 0) + 400000, -3)
    else:
        a.replacement_cost = float({25: 4200, 37.5: 4800, 50: 5600, 75: 9000, 100: 10500, 167: 15500, 300: 32000, 500: 46000}.get(a.rating_kva, 6000)
                                   + (1800 if a.mounting == "pole" else 2500))


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


def ensure_assets(s: Session) -> int:
    """Seed a synthetic asset register once (new and existing databases). Older, tree-heavy circuits get older plant."""
    if s.scalar(select(Asset.id).limit(1)):
        return 0
    import zlib
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

    def add(a: Asset, customers: float, critical: bool) -> None:
        score(a, customers, critical, year)
        rows.append({c.key: getattr(a, c.key) for c in Asset.__table__.columns})

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
            add(a, sub_customers.get(sub.id, 0) / n, sub.id in sub_crit)

    per = density()
    for f in feeders:
        z = zones[f.zone_id]
        rng = random.Random(zlib.crc32(f.id.encode()))
        n = max(4, round(f.customers / per))
        vintage = 8 + 24 * rng.random() ** 0.9 * (0.6 + 0.6 * z.vulnerability) + max(0, year - f.last_trimmed)
        cust_each = f.customers / n
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
            add(a, cust_each, f.id in crit)
    for i in range(0, len(rows), 5000):
        s.execute(insert(Asset), rows[i:i + 5000])
    s.commit()
    return len(rows)


def rescore(s: Session, ids: list[str] | None = None) -> int:
    """Recompute health and risk (after an import, or a new year)."""
    year = utcnow().year
    feeders = {f.id: f for f in s.scalars(select(Feeder)).all()}
    crit = {f.feeder_id for f in s.scalars(select(Facility)).all()}
    counts = dict(s.execute(select(Asset.feeder_id, func.count(Asset.id)).where(Asset.kind == DIST).group_by(Asset.feeder_id)).all())
    sub_cust: dict[str, int] = {}
    for f in feeders.values():
        if f.substation_id:
            sub_cust[f.substation_id] = sub_cust.get(f.substation_id, 0) + f.customers
    sub_n = dict(s.execute(select(Asset.substation_id, func.count(Asset.id)).where(Asset.kind == POWER).group_by(Asset.substation_id)).all())
    sub_crit = {f.substation_id for f in feeders.values() if f.id in crit}
    q = select(Asset) if ids is None else select(Asset).where(Asset.id.in_(ids))
    n = 0
    for a in s.scalars(q).all():
        if a.kind == POWER:
            score(a, sub_cust.get(a.substation_id, 0) / max(1, sub_n.get(a.substation_id, 1)), a.substation_id in sub_crit, year)
        else:
            f = feeders.get(a.feeder_id)
            score(a, (f.customers / max(1, counts.get(a.feeder_id, 1))) if f else density(), a.feeder_id in crit, year)
        n += 1
    s.flush()
    return n


# ---------------------------------------------------------------- rollups
def _aggregates(year: int):
    age = year - Asset.install_year
    poor = case((Asset.condition.in_(POOR), 1), else_=0)
    over = case(((year - Asset.install_year) > case((Asset.kind == POWER, 45), (Asset.mounting == "pad", 40), else_=35), 1), else_=0)
    replace_cost = case((Asset.condition.in_(POOR), Asset.replacement_cost), else_=0)
    return (func.count(Asset.id), func.avg(age), func.max(age), func.avg(Asset.health_index), func.sum(poor), func.sum(over),
            func.sum(Asset.pof_12m), func.sum(Asset.risk_score), func.sum(replace_cost), func.sum(case((Asset.condition == "Critical", 1), else_=0)))


def _row(vals) -> dict:
    n, age, oldest, hi, poor, over, pof, risk, capex, critical = vals
    n = n or 0
    return {"xfmrs": n, "mean_age": round(age or 0, 1), "oldest": int(oldest or 0), "mean_hi": round(hi or 0, 1),
            "poor": int(poor or 0), "critical": int(critical or 0), "pct_poor": round((poor or 0) / n, 4) if n else 0,
            "pct_over_life": round((over or 0) / n, 4) if n else 0, "expected_failures": round(pof or 0, 1),
            "risk": round(risk or 0, 1), "replacement_capex": round(capex or 0)}


def circuit_factors(s: Session) -> dict[str, dict]:
    """Per circuit, what the storm prediction needs: mean health index, Poor/Critical share, mean age, transformer count."""
    year = utcnow().year
    rows = s.execute(select(Asset.feeder_id, func.avg(Asset.health_index), func.avg(case((Asset.condition.in_(POOR), 1.0), else_=0.0)),
                            func.avg(year - Asset.install_year), func.count(Asset.id))
                     .where(Asset.kind == DIST, Asset.feeder_id.is_not(None)).group_by(Asset.feeder_id)).all()
    return {fid: {"hi": hi, "poor": poor, "age": age, "xfmrs": n} for fid, hi, poor, age, n in rows}


def circuit_health(s: Session, region: str | None = None, zone: str | None = None) -> list[dict]:
    from .ops import network_index
    year = utcnow().year
    idx = network_index(s)
    rows = s.execute(select(Asset.feeder_id, *_aggregates(year)).where(Asset.kind == DIST).group_by(Asset.feeder_id)).all()
    feeders = {f.id: f for f in s.scalars(select(Feeder)).all()}
    crit = {f.feeder_id: f.name for f in s.scalars(select(Facility)).all()}
    out = []
    for fid, *vals in rows:
        info, f = idx.get(fid, {}), feeders.get(fid)
        if region and info.get("region_id") != region or zone and info.get("zone_id") != zone:
            continue
        out.append({"id": fid, "zone_id": info.get("zone_id"), "zone": info.get("zone"), "region_id": info.get("region_id"),
                    "region": info.get("region"), "substation_id": info.get("substation_id"), "substation": info.get("substation"),
                    "customers": f.customers if f else 0, "overhead_pct": f.overhead_pct if f else None,
                    "critical_facility": crit.get(fid), **_row(vals)})
    out.sort(key=lambda r: -r["risk"])
    return out


def region_health(s: Session) -> list[dict]:
    year = utcnow().year
    regions = {r.id: r.name for r in s.scalars(select(Region)).all()}
    out = []
    for rid, *vals in s.execute(select(Zone.region_id, *_aggregates(year)).select_from(Asset).join(Zone, Zone.id == Asset.zone_id)
                                .where(Asset.kind == DIST).group_by(Zone.region_id)).all():
        r = _row(vals)
        circuits = s.scalar(select(func.count(Feeder.id)).join(Zone, Zone.id == Feeder.zone_id).where(Zone.region_id == rid))
        pts = s.execute(select(*_aggregates(year)).select_from(Asset).join(Zone, Zone.id == Asset.zone_id)
                        .where(Asset.kind == POWER, Zone.region_id == rid)).one()
        p = _row(pts)
        out.append({"id": rid, "name": regions.get(rid, "Unassigned"), "circuits": circuits, **r,
                    "power_transformers": p["xfmrs"], "power_poor": p["poor"], "power_mean_age": p["mean_age"],
                    "replacement_capex": r["replacement_capex"] + p["replacement_capex"]})
    out.sort(key=lambda r: r["name"])
    return out


def summary(s: Session) -> dict:
    year = utcnow().year
    d = _row(s.execute(select(*_aggregates(year)).where(Asset.kind == DIST)).one())
    p = _row(s.execute(select(*_aggregates(year)).where(Asset.kind == POWER)).one())
    bands = dict(s.execute(select(Asset.condition, func.count(Asset.id)).where(Asset.kind == DIST).group_by(Asset.condition)).all())
    pbands = dict(s.execute(select(Asset.condition, func.count(Asset.id)).where(Asset.kind == POWER).group_by(Asset.condition)).all())
    decades = s.execute(select(((year - Asset.install_year) // 10).label("d"), func.count(Asset.id))
                        .where(Asset.kind == DIST).group_by("d").order_by("d")).all()
    return {"distribution": d, "power": p, "bands": {b: bands.get(b, 0) for b, _ in BANDS}, "power_bands": {b: pbands.get(b, 0) for b, _ in BANDS},
            "age_histogram": [{"decade": f"{int(k) * 10}–{int(k) * 10 + 9} y", "count": n} for k, n in decades],
            "regions": region_health(s), "replacement_capex": d["replacement_capex"] + p["replacement_capex"],
            "density": density()}


def serial(a: Asset, year: int | None = None) -> dict:
    year = year or utcnow().year
    return {"id": a.id, "kind": a.kind, "name": a.name, "substation_id": a.substation_id, "feeder_id": a.feeder_id, "zone_id": a.zone_id,
            "lat": a.lat, "lng": a.lng, "install_year": a.install_year, "age": year - a.install_year, "manufacturer": a.manufacturer,
            "rating_kva": a.rating_kva, "mounting": a.mounting, "phases": a.phases, "last_inspection": a.last_inspection,
            "inspection_score": a.inspection_score, "peak_load_pct": a.peak_load_pct, "dga_tdcg_ppm": a.dga_tdcg_ppm,
            "oil_moisture_ppm": a.oil_moisture_ppm, "through_faults": a.through_faults, "ltc": a.ltc,
            "maintenance_overdue": a.maintenance_overdue, "health_index": a.health_index, "condition": a.condition,
            "pof_12m": a.pof_12m, "risk_score": a.risk_score, "replacement_cost": a.replacement_cost, "drivers": a.drivers or []}


def circuit_detail(s: Session, feeder_id: str, limit: int = 50, offset: int = 0, sort: str = "risk") -> dict | None:
    year = utcnow().year
    rows = [r for r in circuit_health(s) if r["id"] == feeder_id]
    if not rows:
        return None
    c = rows[0]
    order = {"risk": Asset.risk_score.desc(), "age": Asset.install_year.asc(), "health": Asset.health_index.asc()}.get(sort, Asset.risk_score.desc())
    q = select(Asset).where(Asset.kind == DIST, Asset.feeder_id == feeder_id)
    units = s.scalars(q.order_by(order).offset(offset).limit(limit)).all()
    decades = s.execute(select(((year - Asset.install_year) // 10).label("d"), func.count(Asset.id))
                        .where(Asset.kind == DIST, Asset.feeder_id == feeder_id).group_by("d").order_by("d")).all()
    hi_bins = s.execute(select(cast(func.min(Asset.health_index, 99.9) / 10, Integer).label("b"), func.count(Asset.id))
                        .where(Asset.kind == DIST, Asset.feeder_id == feeder_id).group_by("b").order_by("b")).all()
    bands = dict(s.execute(select(Asset.condition, func.count(Asset.id)).where(Asset.kind == DIST, Asset.feeder_id == feeder_id)
                           .group_by(Asset.condition)).all())
    power = s.scalars(select(Asset).where(Asset.kind == POWER, Asset.substation_id == c["substation_id"]).order_by(Asset.id)).all() \
        if c["substation_id"] else []
    f = s.get(Feeder, feeder_id)
    return {**c, "route": f.route if f else None, "bands": {b: bands.get(b, 0) for b, _ in BANDS},
            "age_histogram": [{"decade": f"{int(k) * 10}–{int(k) * 10 + 9} y", "count": n} for k, n in decades],
            "hi_histogram": [{"band": f"{int(k) * 10}–{int(k) * 10 + 10}", "count": n} for k, n in hi_bins],
            "transformers": [serial(a, year) for a in units], "offset": offset, "limit": limit,
            "power_transformers": [serial(a, year) for a in power]}


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


def top_risk(s: Session, n: int = 10, region: str | None = None) -> list[dict]:
    q = select(Asset).order_by(Asset.risk_score.desc())
    if region:
        zones = [z for (z,) in s.execute(select(Zone.id).where(Zone.region_id == region)).all()]
        q = q.where(Asset.zone_id.in_(zones))
    year = utcnow().year
    return [serial(a, year) for a in s.scalars(q.limit(n)).all()]


# ---------------------------------------------------------------- import
FIELDS = ("id", "kind", "name", "substation_id", "feeder_id", "lat", "lng", "install_year", "manufacturer", "rating_kva", "mounting",
          "phases", "last_inspection", "inspection_score", "peak_load_pct", "dga_tdcg_ppm", "oil_moisture_ppm", "through_faults", "ltc",
          "maintenance_overdue")
SAMPLE_CSV = ("id,kind,feeder_id,substation_id,install_year,rating_kva,mounting,inspection_score,peak_load_pct,dga_tdcg_ppm\n"
              "DT-NEW-0001,dist_transformer,{feeder},,1978,50,pole,4,112,\n"
              "PT-NEW-1,power_transformer,,{sub},1969,28000,sub,3,96,2400\n")


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
    """Load the utility's asset register: one row per transformer, matched by id (update) or added. replace=True clears
    the sandbox register first."""
    reader = csv.DictReader(io.StringIO(text.strip()))
    if not reader.fieldnames or "id" not in [f.strip().lower() for f in reader.fieldnames]:
        raise AssetImportError("CSV needs a header row with at least: id, kind, feeder_id or substation_id, install_year")
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
                raise AssetImportError(f"kind must be {' or '.join(KINDS)}")
            if not r.get("id"):
                raise AssetImportError("id is required")
            fid, sid = r.get("feeder_id") or None, r.get("substation_id") or None
            if kind == DIST and fid not in feeders:
                raise AssetImportError(f"unknown feeder_id '{fid}'")
            if kind == POWER and sid not in subs:
                raise AssetImportError(f"unknown substation_id '{sid}'")
            yr = _num(r.get("install_year"), int)
            if yr is None or not 1900 <= yr <= year:
                raise AssetImportError(f"install_year must be between 1900 and {year}")
            sid = sid or (feeders[fid].substation_id if fid else None)
            home = feeders[fid] if fid else None
            zid = home.zone_id if home else subs[sid].zone_id
            lat, lng = _num(r.get("lat")), _num(r.get("lng"))
            if lat is None or lng is None:
                lat, lng = (subs[sid].lat, subs[sid].lng) if kind == POWER else _point_on(home.route, random.Random(r["id"]), zones[zid].lat, zones[zid].lng)
            score_ = _num(r.get("inspection_score"), int)
            if score_ is not None and not 1 <= score_ <= 5:
                raise AssetImportError("inspection_score must be 1–5")
            rows.append({"id": r["id"][:24], "kind": kind, "name": r.get("name") or KINDS[kind], "substation_id": sid, "feeder_id": fid if kind == DIST else None,
                         "zone_id": zid, "lat": lat, "lng": lng, "install_year": yr, "manufacturer": r.get("manufacturer", "")[:40],
                         "rating_kva": _num(r.get("rating_kva")) or (28000.0 if kind == POWER else 50.0),
                         "mounting": r.get("mounting") or ("sub" if kind == POWER else "pole"), "phases": _num(r.get("phases"), int) or (3 if kind == POWER else 1),
                         "last_inspection": _num(r.get("last_inspection"), int), "inspection_score": score_,
                         "peak_load_pct": _num(r.get("peak_load_pct")), "dga_tdcg_ppm": _num(r.get("dga_tdcg_ppm")),
                         "oil_moisture_ppm": _num(r.get("oil_moisture_ppm")), "through_faults": _num(r.get("through_faults"), int),
                         "ltc": r.get("ltc", "").lower() in ("1", "true", "yes", "y"),
                         "maintenance_overdue": r.get("maintenance_overdue", "").lower() in ("1", "true", "yes", "y")})
        except AssetImportError as ex:
            raise AssetImportError(f"Row {i}: {ex}")
    if not rows:
        raise AssetImportError("The file has no asset rows.")
    if replace:
        s.execute(delete(Asset))
    added = updated = 0
    for r in rows:
        a = s.get(Asset, r["id"])
        if a:
            updated += 1
        else:
            a = Asset(id=r["id"])
            s.add(a)
            added += 1
        for k, v in r.items():
            setattr(a, k, v)
    s.flush()
    rescore(s, None if replace else [r["id"] for r in rows])
    return {"added": added, "updated": updated, "total": s.scalar(select(func.count(Asset.id)))}


# ---------------------------------------------------------------- replacement planning
HORIZONS = (0, 5, 10)
_base_cache: dict[tuple, dict] = {}
_new_cache: dict[tuple, tuple] = {}


def _fingerprint(s: Session) -> tuple:
    n, hi, cost = s.execute(select(func.count(Asset.id), func.sum(Asset.health_index), func.sum(Asset.replacement_cost))).one()
    return (str(s.get_bind().url), n, round(hi or 0, 1), round(cost or 0), utcnow().year)


def _project(unit, cons: float, year: int, replaced: bool) -> tuple[float, bool, float]:
    """(pof, poor?, risk) for one unit in `year`: as it ages untouched, or replaced with a new unit this year."""
    from types import SimpleNamespace
    if replaced:  # a new unit's outlook depends only on its type, loading and tap changer: share the result
        key = (unit.kind, unit.mounting, unit.ltc, round(unit.peak_load_pct or 0), year)
        hit = _new_cache.get(key)
        if hit is None:
            a = SimpleNamespace(**{**vars(unit), "install_year": utcnow().year, "inspection_score": 1, "through_faults": 0,
                                   "maintenance_overdue": False, "dga_tdcg_ppm": 150.0 if unit.kind == POWER else None,
                                   "oil_moisture_ppm": 8.0 if unit.kind == POWER else None})
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
    state (a few seconds on ~90k units; warmed at startup) and filtered by region or kind for each plan."""
    from types import SimpleNamespace
    key = _fingerprint(s)
    base = _base_cache.get(key)
    if base is not None:
        return base
    year = utcnow().year
    fleet = []
    cols = ("id", "kind", "name", "install_year", "mounting", "inspection_score", "last_inspection", "peak_load_pct", "dga_tdcg_ppm",
            "oil_moisture_ppm", "through_faults", "ltc", "maintenance_overdue", "rating_kva", "health_index", "condition", "pof_12m",
            "risk_score", "replacement_cost", "feeder_id", "substation_id", "zone_id", "drivers")
    for row in s.execute(select(*(getattr(Asset, c) for c in cols), Zone.region_id).join(Zone, Zone.id == Asset.zone_id)).all():
        a = SimpleNamespace(**dict(zip(cols, row[:-1])))
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
        _base(s)


def replacement_plan(s: Session, budget: float, region: str | None = None, kind: str | None = None, items: int = 150) -> dict:
    """Which transformers to replace for a budget: ranked by risk removed per dollar (customer-outages a year avoided, averaged
    over now, +5 and +10 years so ageing counts), taken greedily until the budget is spent. Also the fleet's condition now and
    in 5 and 10 years, with no action and with the plan. A replaced unit is new; the rest keep ageing with today's inspection
    and oil results (a conservative no-action case)."""
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
        "by_kind": {POWER: sum(1 for i in chosen if fleet[i]["a"].kind == POWER), DIST: sum(1 for i in chosen if fleet[i]["a"].kind == DIST)},
        "poor_replaced": sum(1 for i in chosen if fleet[i]["a"].condition in POOR),
        "risk_reduced_pct": round(1 - projection[0]["with_plan"]["risk"] / now_risk, 4),
        "failures_avoided": round(projection[0]["no_action"]["expected_failures"] - projection[0]["with_plan"]["expected_failures"], 1),
        "projection": projection, "frontier": frontier,
        "by_region": sorted(({**r, "cost": round(r["cost"]), "risk_reduced": round(r["risk_reduced"], 1)} for r in by_region.values()),
                            key=lambda r: -r["risk_reduced"]),
        "items": [{"id": fleet[i]["a"].id, "kind": fleet[i]["a"].kind, "name": fleet[i]["a"].name,
                   "where": fleet[i]["a"].feeder_id or fleet[i]["a"].substation_id, "region": regions.get(fleet[i]["region_id"]),
                   "age": year - fleet[i]["a"].install_year, "health_index": fleet[i]["a"].health_index, "condition": fleet[i]["a"].condition,
                   "cost": fleet[i]["a"].replacement_cost, "risk_reduced": round(gain[i], 2), "drivers": (fleet[i]["a"].drivers or [])[:2]}
                  for i in sorted(chosen, key=lambda i: -gain[i])[:items]],
    }
