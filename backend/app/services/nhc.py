"""National Hurricane Center feed — active Atlantic / East Pacific storms (free, no key).

https://www.nhc.noaa.gov/CurrentStorms.json
The feed gives the current position, intensity and motion. The forecast track is published as
GIS shapefiles; for import we project the track forward from the reported motion vector.
"""
import math
from datetime import datetime, timedelta, timezone

import httpx

FEED = "https://www.nhc.noaa.gov/CurrentStorms.json"
CLASSIFICATION = {"TD": "Tropical Depression", "TS": "Tropical Storm", "HU": "Hurricane", "MH": "Major Hurricane",
                  "STD": "Subtropical Depression", "STS": "Subtropical Storm", "PTC": "Post-tropical Cyclone", "TY": "Typhoon"}
TAMPA = (27.95, -82.46)


def kt_to_mph(kt: float) -> int:
    return round(kt * 1.15078)


def saffir_simpson(mph: int) -> int:
    for cat, lo in ((5, 157), (4, 130), (3, 111), (2, 96), (1, 74)):
        if mph >= lo:
            return cat
    return 0


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse(feed: dict) -> list[dict]:
    storms = []
    for st in feed.get("activeStorms", []):
        lat, lng = _num(st.get("latitudeNumeric")), _num(st.get("longitudeNumeric"))
        if lat is None or lng is None:
            continue
        mph = kt_to_mph(_num(st.get("intensity")) or 0)
        heading = _num(st.get("movementDir")) or 0
        speed_mph = kt_to_mph(_num(st.get("movementSpeed")) or 0)
        updated = st.get("lastUpdate")
        try:
            at = datetime.fromisoformat(updated.replace("Z", "+00:00")) if updated else datetime.now(timezone.utc)
        except ValueError:
            at = datetime.now(timezone.utc)
        dist = math.hypot((lat - TAMPA[0]) * 69, (lng - TAMPA[1]) * 69 * math.cos(math.radians(lat)))
        storms.append({
            "nhc_id": st.get("id", ""), "name": st.get("name", "Unnamed"),
            "kind": CLASSIFICATION.get(st.get("classification", ""), st.get("classification", "")),
            "lat": lat, "lng": lng, "wind_mph": mph, "category": saffir_simpson(mph),
            "pressure_mb": int(_num(st.get("pressure")) or 0), "heading_deg": heading, "speed_mph": speed_mph,
            "movement": f"{_compass(heading)} at {speed_mph} mph", "updated_at": at.isoformat(),
            "distance_to_tampa_mi": round(dist), "advisory_url": (st.get("publicAdvisory") or {}).get("url", ""),
        })
    return storms


def _compass(deg: float) -> str:
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[round(deg / 22.5) % 16]


def project_track(lat: float, lng: float, heading_deg: float, speed_mph: float, start: datetime, hours: int = 120) -> list[dict]:
    """Straight-line projection from the current motion vector, every 12 h."""
    pts = [{"lat": lat, "lng": lng, "at": start.isoformat(), "observed": True}]
    for h in range(12, hours + 1, 12):
        d = speed_mph * h
        dlat = d * math.cos(math.radians(heading_deg)) / 69
        dlng = d * math.sin(math.radians(heading_deg)) / (69 * math.cos(math.radians(lat)))
        pts.append({"lat": round(lat + dlat, 2), "lng": round(lng + dlng, 2), "at": (start + timedelta(hours=h)).isoformat(), "observed": False})
    return pts


async def fetch() -> dict:
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "OMS360 storm operations"}) as c:
        r = await c.get(FEED)
        r.raise_for_status()
        return r.json()
