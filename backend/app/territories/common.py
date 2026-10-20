"""Reference data shared by every territory: hazard damage curves, channels and defaults."""
import math
from datetime import timedelta

# Hurricanes: Saffir-Simpson category → territory-wide damage factor, sustained wind and surge.
CATF = {1: 0.07, 2: 0.17, 3: 0.33, 4: 0.52, 5: 0.74}
WIND_BY_CAT = {0: 65, 1: 85, 2: 105, 3: 120, 4: 140, 5: 165}
SURGE_BY_CAT = {1: "4–6 ft", 2: "6–9 ft", 3: "9–12 ft", 4: "12–16 ft", 5: "16–20 ft"}

# Tornadoes: Enhanced Fujita rating → peak 3-second gust (mph, lower bound of the class) and the share of overhead
# customers a circuit loses where its line crosses the core damage path. Calibrated on Moore 2013, Joplin 2011 and
# the 2024 Oklahoma outbreaks: EF0–1 mostly tree and service damage, EF3+ snaps poles and destroys transformers.
EF_WIND = {0: 65, 1: 86, 2: 111, 3: 136, 4: 166, 5: 200}
EF_DAMAGE = {0: 0.15, 1: 0.35, 2: 0.6, 3: 0.8, 4: 0.92, 5: 0.97}
EF_WIDTH_M = {0: 100, 1: 200, 2: 400, 3: 700, 4: 1200, 5: 1600}  # typical damage-path width when none is given

INTERNAL = {"line": 640, "tree": 180, "da": 40}
LIFT_STATIONS = 412
MEDICAL_NEEDS = 1240
MUTUAL_AID_DAY_COST = 4200

CHANNELS = [
    {"id": "x", "name": "X / Twitter"},
    {"id": "fb", "name": "Facebook"},
    {"id": "sms", "name": "SMS"},
    {"id": "email", "name": "Email"},
    {"id": "ivr", "name": "IVR / phone"},
]

DEFAULT_TRIGGERS = [
    ("Outage detected by smart meter → SMS within 5 min", True),
    ("AI ETR changes by > 1 hour → SMS + website update", True),
    ("Crew dispatched to your area → SMS", True),
    ('Power restored → "Still out? Reply OUT" SMS', True),
    ("Boil-water advisory issued → SMS + IVR to affected water customers", True),
    ("Auto-publish social posts without human approval", False),
]

SUBSTATION_SIDES = [("North", 0.02, 0.0), ("South", -0.02, 0.0), ("East", 0.0, 0.025), ("West", 0.0, -0.025)]


def address_feeder(address: str, feeder_ids: list[str]) -> str:
    """Sandbox stand-in for the GIS customer→circuit lookup: a stable circuit for each address within its zone."""
    import zlib
    return sorted(feeder_ids)[zlib.crc32(address.lower().encode()) % len(feeder_ids)]


def _km(a, b) -> float:
    return math.hypot((a[0] - b[0]) * 111, (a[1] - b[1]) * 111 * math.cos(math.radians(a[0])))


def path_track(paths: list[dict], impact, now) -> list[dict]:
    """Tornado paths as one flat track: each point carries its path index, EF rating, width and the time the tornado
    passes it (from the path's start offset and forward speed)."""
    out = []
    for i, p in enumerate(paths):
        t = impact + timedelta(hours=p.get("start_h", 0))
        prev = None
        for pt in p["points"]:
            if prev:
                t += timedelta(hours=_km(prev, pt) / (p.get("mph", 30) * 1.609))
            out.append({"lat": pt[0], "lng": pt[1], "at": t.isoformat(), "observed": t <= now, "path": i, "ef": p["ef"],
                        "width_m": p["width_m"]})
            prev = pt
    return out
