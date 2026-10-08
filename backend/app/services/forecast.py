"""Outside storm forecasts (e.g. the parent company's predictive modeling suite).

That suite tracks the storm over the whole region; it doesn't know the utility's circuits. We take its hazard
per zone — peak gust, rainfall, surge and arrival time — and the prediction downscales it to every circuit using
the utility's own network data (overhead exposure, vegetation cycle, flood exposure, crews).

Import formats (Storm event → Impact prediction → Forecast input):
  CSV   zone,gust_mph,rain_in,surge_ft,arrival_at       zone = id, code or name; other columns optional
  JSON  {"source": "...", "issued_at": "...", "zones": [{"zone": "tpa", "gust_mph": 120, ...}]}
The sandbox can also generate a parent-model forecast from the event's track / rainfall (mock feed).
"""
import csv
import io
import math
import random
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..data import SURGE_BY_CAT, TRACK, WIND_BY_CAT
from ..models import ForecastRun, StormEvent, Zone, utcnow
from .events import is_rain

PARENT_SOURCE = "Parent-company storm model"
FIELDS = ("gust_mph", "rain_in", "surge_ft")
LIMITS = {"gust_mph": (0, 250), "rain_in": (0, 40), "surge_ft": (0, 30)}


class ForecastError(ValueError):
    pass


def latest_forecast(s: Session, event_id: int) -> ForecastRun | None:
    return s.scalars(select(ForecastRun).where(ForecastRun.event_id == event_id).order_by(ForecastRun.id.desc())).first()


def _km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    return math.hypot((lat1 - lat2) * 111, (lng1 - lng2) * 111 * math.cos(math.radians(lat1)))


def mock_parent_forecast(s: Session, e: StormEvent, seed: int | None = None) -> list[dict]:
    """Sandbox stand-in for the parent model's output: hazard decays with distance from the forecast track
    (hurricanes) or follows a north–south rainfall gradient (rain events). Scaled so the territory as a whole matches
    the event's advisory intensity (category / rainfall total): the parent model adds where, not how strong."""
    from .prediction import wind_factor
    from ..data import CATF
    rng = random.Random(seed if seed is not None else e.id * 7919)
    zones = s.scalars(select(Zone)).all()
    total_cust = sum(z.customers for z in zones)
    onset = e.landfall_at or utcnow() + timedelta(hours=48)
    out = []
    if is_rain(e):
        total = e.rain_total_in or 4.0
        shape = {}
        for z in zones:
            south = min(1.0, max(0.0, (28.05 - z.lat) / 0.33))  # bands stall over the South Shore
            shape[z.id] = (south, (0.7 + 0.6 * south) * rng.uniform(0.92, 1.08))
        k = total / (sum(shape[z.id][1] * z.customers for z in zones) / total_cust)
        for z in zones:
            south, f = shape[z.id]
            out.append({"zone_id": z.id, "gust_mph": round(rng.uniform(25, 40)), "rain_in": round(min(40, k * f), 1), "surge_ft": 0.0,
                        "arrival_at": (onset + timedelta(hours=(1 - south) * 3)).isoformat()})
        return out
    cat = max(1, min(5, e.category))
    pts = [(p["lat"], p["lng"]) for p in (e.track or [])] or [(TRACK[4][0], TRACK[4][1])]
    lo, hi = (float(x) for x in SURGE_BY_CAT[cat].replace(" ft", "").split("–"))
    dist = {z.id: min(_km(z.lat, z.lng, la, ln) for la, ln in pts) for z in zones}
    shape = {z.id: max(0.55, math.exp(-dist[z.id] / 140)) * rng.uniform(0.95, 1.05) for z in zones}
    lo_g, hi_g = 40.0, 300.0  # find the peak gust whose customer-weighted damage matches the advisory category
    for _ in range(40):
        mid = (lo_g + hi_g) / 2
        mean = sum(wind_factor(mid * shape[z.id]) * z.customers for z in zones) / total_cust
        lo_g, hi_g = (mid, hi_g) if mean < CATF[cat] else (lo_g, mid)
    for z in zones:
        d = dist[z.id]
        out.append({"zone_id": z.id, "gust_mph": round(min(250, lo_g * shape[z.id])),
                    "rain_in": round((4 + 1.5 * cat) * math.exp(-d / 160) * rng.uniform(0.9, 1.1), 1),
                    "surge_ft": round((lo + hi) / 2 * math.exp(-d / 50), 1) if z.coastal else 0.0,
                    "arrival_at": (onset + timedelta(hours=d / 30 - 1)).isoformat()})
    return out


def normalize(s: Session, rows: list[dict]) -> list[dict]:
    """Match each row to a zone (id, code or name) and validate the hazard values."""
    zones = s.scalars(select(Zone)).all()
    keys = {k.lower(): z.id for z in zones for k in (z.id, z.code, z.short, z.name)}
    out: dict[str, dict] = {}
    for i, r in enumerate(rows, 1):
        ref = str(r.get("zone") or r.get("zone_id") or "").strip().lower()
        if ref not in keys:
            raise ForecastError(f"Row {i}: unknown zone '{ref}'. Use a zone id, code or name, e.g. tpa, TPA or Tampa.")
        h = {"zone_id": keys[ref]}
        for f in FIELDS:
            v = r.get(f)
            if v in (None, ""):
                continue
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise ForecastError(f"Row {i}: {f} must be a number.")
            lo, hi = LIMITS[f]
            if not lo <= v <= hi:
                raise ForecastError(f"Row {i}: {f} must be between {lo} and {hi}.")
            h[f] = v
        if not any(f in h for f in ("gust_mph", "rain_in")):
            raise ForecastError(f"Row {i}: give at least gust_mph or rain_in.")
        if r.get("arrival_at"):
            try:
                h["arrival_at"] = datetime.fromisoformat(str(r["arrival_at"]).replace("Z", "+00:00")).isoformat()
            except ValueError:
                raise ForecastError(f"Row {i}: arrival_at must be an ISO date-time, e.g. 2026-10-09T18:00:00-04:00.")
        out[h["zone_id"]] = h
    if not out:
        raise ForecastError("The forecast has no zone rows.")
    return list(out.values())


def parse_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text.strip()))
    if not reader.fieldnames or "zone" not in [f.strip().lower() for f in reader.fieldnames]:
        raise ForecastError("CSV needs a header row with a 'zone' column, e.g. zone,gust_mph,rain_in,surge_ft,arrival_at")
    return [{k.strip().lower(): (v or "").strip() for k, v in row.items() if k} for row in reader]


def complete(s: Session, e: StormEvent, zones: list[dict]) -> list[dict]:
    """Zones the import left out keep the event-wide intensity, so a partial forecast still covers the territory."""
    have = {h["zone_id"] for h in zones}
    rain = is_rain(e)
    filler = {"gust_mph": 30.0, "rain_in": e.rain_total_in or 4.0} if rain else {"gust_mph": WIND_BY_CAT[max(1, min(5, e.category))] * 1.25}
    return zones + [{"zone_id": z.id, **filler, "filled": True} for z in s.scalars(select(Zone)).all() if z.id not in have]


def save(s: Session, e: StormEvent, zones: list[dict], source: str, user: str, issued_at: datetime | None = None) -> ForecastRun:
    fc = ForecastRun(event_id=e.id, source=source[:80], issued_at=issued_at or utcnow(), zones=complete(s, e, zones), created_by=user)
    s.add(fc)
    s.flush()
    return fc


def serial(fc: ForecastRun, zone_names: dict[str, str]) -> dict:
    return {"id": fc.id, "source": fc.source, "issued_at": fc.issued_at, "created_by": fc.created_by, "created_at": fc.created_at,
            "zones": [h | {"zone": zone_names.get(h["zone_id"], h["zone_id"])} for h in fc.zones]}


SAMPLE_CSV = "zone,gust_mph,rain_in,surge_ft,arrival_at\n" + "\n".join([
    "tpa,128,9.5,8.5,", "apb,135,8.0,11.0,", "rsk,131,7.5,10.0,", "brn,104,7.0,0,", "plc,88,5.5,0,", "ltz,92,6.0,0,"])
