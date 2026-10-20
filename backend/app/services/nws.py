"""National Weather Service alerts feed — active tornado and severe-thunderstorm warnings and watches (free, no key).

https://api.weather.gov/alerts/active?area=OK
A tornado warning carries the storm's radar position and motion ("eventMotionDescription") and how the tornado was
detected / how much damage it threatens. Imported, it becomes a Tornado event with a planning damage path projected
along that motion until the warning expires; after the storm, the NWS damage survey replaces it (PUT /events/{id}/paths).
"""
import re
from datetime import datetime, timedelta, timezone

import httpx

from ..data import EF_WIDTH_M, STATE_CODE

FEED = "https://api.weather.gov/alerts/active"
EVENTS = ("Tornado Warning", "Tornado Watch", "Severe Thunderstorm Warning", "Severe Thunderstorm Watch", "Tornado Emergency")
MOTION = re.compile(r"\.\.\.(\d{1,3})DEG\.\.\.(\d{1,3})KT\.\.\.([\d ]+)")


def _iso(v: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None
    except ValueError:
        return None


def ef_estimate(params: dict) -> int:
    """A planning EF rating from the warning's tags: a tornado emergency (CATASTROPHIC) is planned as EF4,
    CONSIDERABLE damage threat as EF3, a confirmed (OBSERVED) tornado as EF2, radar-indicated as EF1."""
    threat = " ".join(params.get("tornadoDamageThreat", [])).upper()
    detection = " ".join(params.get("tornadoDetection", [])).upper()
    if "CATASTROPHIC" in threat:
        return 4
    if "CONSIDERABLE" in threat:
        return 3
    return 2 if "OBSERVED" in detection else 1


def motion(params: dict) -> dict | None:
    """'2024-05-06T23:34:00-00:00...storm...245DEG...30KT...3512 9750' → position, heading toward and speed.
    NWS gives the direction the storm moves FROM, and positions as lat×100 / west lon×100."""
    for raw in params.get("eventMotionDescription", []):
        m = MOTION.search(raw)
        if not m:
            continue
        nums = [int(x) for x in m.group(3).split()]
        if len(nums) < 2:
            continue
        frm, kt = int(m.group(1)), int(m.group(2))
        return {"lat": nums[0] / 100, "lng": -nums[1] / 100, "heading_deg": (frm + 180) % 360, "speed_mph": round(kt * 1.15078),
                "at": _iso(raw.split("...")[0])}
    return None


def _centroid(geom: dict | None) -> tuple[float, float] | None:
    if not geom or geom.get("type") != "Polygon":
        return None
    ring = geom["coordinates"][0]
    return sum(p[1] for p in ring) / len(ring), sum(p[0] for p in ring) / len(ring)


def parse(feed: dict) -> list[dict]:
    out = []
    for f in feed.get("features", []):
        p = f.get("properties") or {}
        event = p.get("event", "")
        if event not in EVENTS:
            continue
        params = p.get("parameters") or {}
        mv = motion(params)
        c = _centroid(f.get("geometry"))
        polygon = [[pt[1], pt[0]] for pt in f["geometry"]["coordinates"][0]] if f.get("geometry", {}) and f["geometry"].get("type") == "Polygon" else []
        ef = ef_estimate(params) if "Tornado" in event else None
        out.append({"id": p.get("id") or f.get("id", ""), "event": event, "headline": p.get("headline") or event, "area": p.get("areaDesc", ""),
                    "severity": p.get("severity", ""), "onset": p.get("onset") or p.get("effective"), "expires": p.get("expires") or p.get("ends"),
                    "ef_estimate": ef, "detection": ", ".join(params.get("tornadoDetection", [])),
                    "damage_threat": ", ".join(params.get("tornadoDamageThreat", [])), "max_hail": ", ".join(params.get("maxHailSize", [])),
                    "motion": mv, "lat": (mv or {}).get("lat") or (c[0] if c else None), "lng": (mv or {}).get("lng") or (c[1] if c else None),
                    "polygon": polygon, "importable": event in ("Tornado Warning", "Tornado Emergency") and bool(mv or c)})
    order = {e: i for i, e in enumerate(("Tornado Emergency", "Tornado Warning", "Tornado Watch", "Severe Thunderstorm Warning", "Severe Thunderstorm Watch"))}
    out.sort(key=lambda a: order.get(a["event"], 9))
    return out


def warning_path(alert: dict, now: datetime | None = None) -> dict:
    """The planning damage path for a tornado warning: from the radar position along the storm motion until the warning
    expires (at least 20 min, at most 90)."""
    now = now or datetime.now(timezone.utc)
    mv = alert.get("motion") or {"lat": alert["lat"], "lng": alert["lng"], "heading_deg": 45, "speed_mph": 30, "at": None}
    start = mv.get("at") or _iso(alert.get("onset")) or now
    end = _iso(alert.get("expires")) or start + timedelta(minutes=45)
    minutes = max(20.0, min(90.0, (end - start).total_seconds() / 60))
    length_mi = mv["speed_mph"] * minutes / 60
    ef = alert.get("ef_estimate") or 1
    import math
    n = max(2, round(length_mi / 2))
    pts = []
    for i in range(n + 1):
        d = length_mi * i / n
        pts.append([round(mv["lat"] + d * math.cos(math.radians(mv["heading_deg"])) / 69, 4),
                    round(mv["lng"] + d * math.sin(math.radians(mv["heading_deg"])) / (69 * math.cos(math.radians(mv["lat"]))), 4)])
    return {"ef": ef, "width_m": EF_WIDTH_M[ef], "start_h": 0, "mph": max(5, mv["speed_mph"]), "points": pts, "touchdown": start,
            "length_mi": round(length_mi, 1)}


async def fetch(area: str = STATE_CODE) -> dict:
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "OMS360 storm operations (contact: ops@example.com)",
                                                      "Accept": "application/geo+json"}) as c:
        r = await c.get(FEED, params={"area": area})
        r.raise_for_status()
        return r.json()


def sample_feed(now: datetime | None = None) -> dict:
    """Sandbox: one tornado warning in the NWS GeoJSON format, just southwest of the territory's main city, so the import can
    be shown when the real feed is quiet. Parsed by the same code as live alerts."""
    from ..data import WEATHER_POINT
    now = now or datetime.now(timezone.utc)
    lat, lng = WEATHER_POINT["lat"] - 0.12, WEATHER_POINT["lon"] - 0.18
    ring = [[lng - 0.12, lat - 0.06], [lng + 0.32, lat + 0.14], [lng + 0.36, lat + 0.24], [lng - 0.06, lat + 0.04], [lng - 0.12, lat - 0.06]]
    stamp = now.strftime("%Y-%m-%dT%H:%M:00-00:00")
    return {"features": [{"id": "sandbox-tornado-warning", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": {
        "id": f"urn:oid:sandbox.tornado.{now:%Y%m%d%H%M}", "event": "Tornado Warning", "severity": "Extreme",
        "headline": "Tornado Warning (sandbox sample) — confirmed tornado moving northeast at 35 mph",
        "areaDesc": "Sandbox County", "onset": now.isoformat(), "expires": (now + timedelta(minutes=45)).isoformat(),
        "parameters": {"tornadoDetection": ["OBSERVED"], "tornadoDamageThreat": ["CONSIDERABLE"], "maxHailSize": ["2.00"],
                       "eventMotionDescription": [f"{stamp}...storm...230DEG...30KT...{round(lat * 100)} {round(-lng * 100)}"]}}}]}
