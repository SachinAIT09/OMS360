"""Static reference data for the demo utility "Bayview Power & Water" (fictional),
serving Hillsborough County, FL. Zone coordinates are real community locations."""
from datetime import datetime, timedelta, timezone

EDT = timezone(timedelta(hours=-4), "EDT")

# Simulated landfall of Hurricane Kyle at the mouth of Tampa Bay.
LANDFALL = datetime(2026, 10, 6, 20, 0, tzinfo=EDT)

ZONES = [
    {"id": "tpa", "code": "TPA", "name": "Tampa (Downtown / South)", "short": "Tampa", "lat": 27.9420, "lng": -82.4700, "cust": 196000, "water": 52000, "vuln": 0.95, "coastal": True, "crit": True},
    {"id": "tnc", "code": "TNC", "name": "Town 'n' Country", "short": "Town 'n' Country", "lat": 28.0106, "lng": -82.5773, "cust": 62000, "water": 18000, "vuln": 0.90, "coastal": True},
    {"id": "wch", "code": "WCH", "name": "Westchase", "short": "Westchase", "lat": 28.0550, "lng": -82.6093, "cust": 31000, "water": 9000, "vuln": 0.70},
    {"id": "cwd", "code": "CWD", "name": "Carrollwood", "short": "Carrollwood", "lat": 28.0500, "lng": -82.4926, "cust": 48000, "water": 14000, "vuln": 0.65, "crit": True},
    {"id": "ltz", "code": "LTZ", "name": "Lutz", "short": "Lutz", "lat": 28.1511, "lng": -82.4615, "cust": 24000, "water": 6000, "vuln": 0.55},
    {"id": "ttr", "code": "TTR", "name": "Temple Terrace", "short": "Temple Terrace", "lat": 28.0353, "lng": -82.3893, "cust": 29000, "water": 9000, "vuln": 0.60},
    {"id": "brn", "code": "BRN", "name": "Brandon", "short": "Brandon", "lat": 27.9378, "lng": -82.2859, "cust": 86000, "water": 24000, "vuln": 0.70, "crit": True},
    {"id": "val", "code": "VAL", "name": "Valrico", "short": "Valrico", "lat": 27.9467, "lng": -82.2437, "cust": 34000, "water": 10000, "vuln": 0.60},
    {"id": "plc", "code": "PLC", "name": "Plant City", "short": "Plant City", "lat": 28.0186, "lng": -82.1129, "cust": 41000, "water": 12000, "vuln": 0.50, "crit": True},
    {"id": "rvv", "code": "RVV", "name": "Riverview", "short": "Riverview", "lat": 27.8661, "lng": -82.3265, "cust": 72000, "water": 20000, "vuln": 0.80},
    {"id": "apb", "code": "APB", "name": "Apollo Beach", "short": "Apollo Beach", "lat": 27.7731, "lng": -82.4076, "cust": 22000, "water": 6000, "vuln": 1.00, "coastal": True},
    {"id": "rsk", "code": "RSK", "name": "Ruskin", "short": "Ruskin", "lat": 27.7209, "lng": -82.4332, "cust": 26000, "water": 7000, "vuln": 0.95, "coastal": True},
    {"id": "scc", "code": "SCC", "name": "Sun City Center", "short": "Sun City Center", "lat": 27.7181, "lng": -82.3518, "cust": 21000, "water": 6000, "vuln": 0.85, "med": True},
]
for _z in ZONES:
    _z.setdefault("coastal", False)
    _z.setdefault("crit", False)
    _z.setdefault("med", False)

ZONE_BY_ID = {z["id"]: z for z in ZONES}

# Operating regions: groups of zones that share a district office and crew pool.
REGIONS = [
    {"id": "north", "name": "North", "zones": ["tnc", "wch", "cwd", "ltz"]},
    {"id": "central", "name": "Central", "zones": ["tpa", "ttr"]},
    {"id": "east", "name": "East", "zones": ["brn", "val", "plc"]},
    {"id": "south", "name": "South Shore", "zones": ["rvv", "apb", "rsk", "scc"]},
]
SUBSTATION_SIDES = [("North", 0.02, 0.0), ("South", -0.02, 0.0), ("East", 0.0, 0.025), ("West", 0.0, -0.025)]
TOTAL_CUST = sum(z["cust"] for z in ZONES)
TOTAL_WATER = sum(z["water"] for z in ZONES)

FACILITIES = [
    {"name": "Tampa General Hospital", "t": "H", "type": "Hospital", "lat": 27.9373, "lng": -82.4598, "zone": "tpa", "feeder": "FDR-TPA-01", "backup": "96 h diesel"},
    {"name": "St. Joseph's Hospital", "t": "H", "type": "Hospital", "lat": 27.9806, "lng": -82.4869, "zone": "tpa", "feeder": "FDR-TPA-04", "backup": "72 h diesel"},
    {"name": "Brandon Regional Hospital", "t": "H", "type": "Hospital", "lat": 27.9373, "lng": -82.2934, "zone": "brn", "feeder": "FDR-BRN-02", "backup": "72 h diesel"},
    {"name": "South Florida Baptist Hospital", "t": "H", "type": "Hospital", "lat": 28.0136, "lng": -82.1226, "zone": "plc", "feeder": "FDR-PLC-01", "backup": "48 h diesel"},
    {"name": "North Regional Water Treatment", "t": "W", "type": "Water plant", "lat": 28.0640, "lng": -82.4250, "zone": "cwd", "feeder": "FDR-CWD-03", "backup": "Dual feed + 2 MW gen"},
    {"name": "South County Water Reclamation", "t": "W", "type": "Water plant", "lat": 27.7400, "lng": -82.3900, "zone": "rsk", "feeder": "FDR-RSK-01", "backup": "1.5 MW gen"},
    {"name": "County Emergency Operations Ctr", "t": "E", "type": "EOC", "lat": 27.9640, "lng": -82.3720, "zone": "ttr", "feeder": "FDR-TTR-02", "backup": "Dual feed"},
    {"name": "Shelter — Brandon High School", "t": "S", "type": "Shelter", "lat": 27.9330, "lng": -82.2800, "zone": "brn", "feeder": "FDR-BRN-05", "backup": "None — portable gen"},
    {"name": "Shelter — Riverview High School", "t": "S", "type": "Shelter", "lat": 27.8590, "lng": -82.3180, "zone": "rvv", "feeder": "FDR-RVV-03", "backup": "None — portable gen"},
    {"name": "Sun City Center medical cluster", "t": "M", "type": "Medical-needs", "lat": 27.7150, "lng": -82.3550, "zone": "scc", "feeder": "FDR-SCC-01", "backup": "Mixed"},
]

YARDS = [
    {"name": "Stadium North Lot staging", "lat": 27.9790, "lng": -82.5030, "cap": 400},
    {"name": "Plant City Fairgrounds staging", "lat": 28.0146, "lng": -82.1406, "cap": 650},
    {"name": "Brandon Service Center", "lat": 27.9300, "lng": -82.3100, "cap": 260},
    {"name": "Lutz Operations Yard", "lat": 28.1400, "lng": -82.4700, "cap": 220},
]

# Simulated track: Gulf → landfall at mouth of Tampa Bay → inland NE.
TRACK = [[23.6, -86.4], [24.9, -85.6], [26.0, -84.7], [26.9, -83.8], [27.62, -82.72], [28.15, -81.95], [28.75, -81.05]]
TRACK_H = [-108, -72, -48, -24, 0, 24, 48]  # hours relative to landfall for each track point

CATF = {1: 0.07, 2: 0.17, 3: 0.33, 4: 0.52, 5: 0.74}
WIND_BY_CAT = {0: 65, 1: 85, 2: 105, 3: 120, 4: 140, 5: 165}
SURGE_BY_CAT = {1: "4–6 ft", 2: "6–9 ft", 3: "9–12 ft", 4: "12–16 ft", 5: "16–20 ft"}

PHASES = [
    {"key": "prep", "short": "T-72h", "label": "Prepare", "h": -72, "storm": 1, "status": "Hurricane Watch issued for Tampa Bay"},
    {"key": "pre", "short": "T-24h", "label": "Pre-landfall", "h": -24, "storm": 3, "status": "Hurricane Warning in effect"},
    {"key": "impact", "short": "T-0", "label": "Landfall", "h": 0, "storm": 4, "status": "Hurricane conditions — crews sheltered"},
    {"key": "restore", "short": "T+24h", "label": "Restore", "h": 24, "storm": 5, "status": "All-clear for field work — restoration under way"},
    {"key": "recover", "short": "T+72h", "label": "Recover", "h": 72, "storm": 6, "status": "Storm dissipated — final restoration & after-action"},
]

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

SAMPLE_ADDRESSES = [
    ("1208 Bayshore Blvd, Tampa", "tpa"),
    ("455 Lumsden Rd, Brandon", "brn"),
    ("6301 Apollo Beach Blvd, Apollo Beach", "apb"),
    ("10920 Big Bend Rd, Riverview", "rvv"),
    ("1802 Cortaro Dr, Sun City Center", "scc"),
    ("3305 James L Redman Pkwy, Plant City", "plc"),
]

def address_feeder(address: str, feeder_ids: list[str]) -> str:
    """Sandbox stand-in for the GIS customer→circuit lookup: a stable circuit for each address within its zone."""
    import zlib
    return sorted(feeder_ids)[zlib.crc32(address.lower().encode()) % len(feeder_ids)]


TAMPA = {"lat": 27.9506, "lon": -82.4572}
