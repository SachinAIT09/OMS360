"""Territory: the demo utility "Bayview Power & Water" (fictional), serving Hillsborough County, FL.
Hazard: hurricanes (plus rain events). Zone coordinates are real community locations."""
from datetime import datetime, timedelta, timezone

KEY = "tampa"
HAZARD = "hurricane"  # the territory's signature hazard: drives the demo event and default UI vocabulary

# ---------------------------------------------------------------- brand
UTILITY_NAME = "Bayview Power & Water"
UTILITY_SHORT = "Bayview"
SITE = "bayviewpw.example/outages"
EMAIL_DOMAIN = "bayviewpw.example"
CREW_PREFIX = "BV"
AREA = "Tampa Bay"                      # how customers name the region in messages
COUNTY = "Hillsborough County"
STATE = "Florida"
STATE_CODE = "FL"  # NWS alert area
HASHTAG_SUFFIX = "FL"
TZ_NAME = "America/New_York"
WEATHER_POINT = {"lat": 27.9506, "lon": -82.4572}
WEATHER_LABEL = "Tampa"
MAP_CENTER = [27.93, -82.4]
MAP_ZOOM = 10
HAS_WATER = True

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

# Operating regions: groups of zones that share a district office and crew pool.
REGIONS = [
    {"id": "north", "name": "North", "zones": ["tnc", "wch", "cwd", "ltz"]},
    {"id": "central", "name": "Central", "zones": ["tpa", "ttr"]},
    {"id": "east", "name": "East", "zones": ["brn", "val", "plc"]},
    {"id": "south", "name": "South Shore", "zones": ["rvv", "apb", "rsk", "scc"]},
]

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

PHASES = [
    {"key": "prep", "short": "T-72h", "label": "Prepare", "h": -72, "storm": 1, "status": "Hurricane Watch issued for Tampa Bay"},
    {"key": "pre", "short": "T-24h", "label": "Pre-landfall", "h": -24, "storm": 3, "status": "Hurricane Warning in effect"},
    {"key": "impact", "short": "T-0", "label": "Landfall", "h": 0, "storm": 4, "status": "Hurricane conditions — crews sheltered"},
    {"key": "restore", "short": "T+24h", "label": "Restore", "h": 24, "storm": 5, "status": "All-clear for field work — restoration under way"},
    {"key": "recover", "short": "T+72h", "label": "Recover", "h": 72, "storm": 6, "status": "Storm dissipated — final restoration & after-action"},
]

SAMPLE_ADDRESSES = [
    ("1208 Bayshore Blvd, Tampa", "tpa"),
    ("455 Lumsden Rd, Brandon", "brn"),
    ("6301 Apollo Beach Blvd, Apollo Beach", "apb"),
    ("10920 Big Bend Rd, Riverview", "rvv"),
    ("1802 Cortaro Dr, Sun City Center", "scc"),
    ("3305 James L Redman Pkwy, Plant City", "plc"),
]

# ---------------------------------------------------------------- partners
MA_PARTNERS = [("Southern Grid Cooperative", "Georgia", 0.4), ("Carolina Power Alliance", "North Carolina", 0.35),
               ("Tennessee Valley Line Services", "Tennessee", 0.25)]
TREE_PARTNER = ("Gulf States Vegetation", "Alabama")
DA_PARTNER = ("Peninsula Damage Assessment", "Florida")
HISTORY_MA = [("Southern Grid Cooperative", "Georgia", 120), ("Carolina Power Alliance", "North Carolina", 80)]  # workers per category

# ---------------------------------------------------------------- demo scenario
DEMO_EVENT = {"name": "Hurricane Kyle", "kind": "Hurricane", "category": 3, "max_wind_mph": 105, "pressure_mb": 968,
              "movement": "NNE at 12 mph", "hours_out": 72,
              "notes": "Forecast landfall near the mouth of Tampa Bay. Planning scenario based on the latest advisory package."}
NEW_EVENT = {"kind": "Hurricane", "lat": 25.5, "lng": -85.5}  # defaults for the create-event form
HISTORY_POSITION = (27.6, -82.7)
HISTORICAL = [
    {"name": "Hurricane Delphine", "category": 2, "days_ago": 390, "actual": 0.93},
    {"name": "Hurricane Barrett", "category": 1, "days_ago": 118, "actual": 1.08},
    # own generator, so adding it leaves the rest of the seeded demo unchanged
    {"name": "June Rain Event", "category": 1, "days_ago": 60, "actual": 1.04, "rng": 7,
     "rain": {"rain_total_in": 7.5, "rain_rate_in_hr": 1.8, "duration_h": 18, "soil_saturation": 0.8}},
]
RAIN_DEMO = {"name": "Tampa Bay Rain Event", "lat": 27.95, "lng": -82.46, "worst": ["Ruskin", "Apollo Beach"],
             "notes": "Stalled frontal boundary over Tampa Bay. 5–8 in observed, locally 10 in along the South Shore; streets flooded in Ruskin and Apollo Beach."}
RAIN_GRADIENT = {"ref_lat": 28.05, "spread": 0.33, "sign": -1}  # rain bands stall over the South Shore (south of ref_lat)
SAMPLE_FORECAST_CSV = "zone,gust_mph,rain_in,surge_ft,arrival_at\n" + "\n".join([
    "tpa,128,9.5,8.5,", "apb,135,8.0,11.0,", "rsk,131,7.5,10.0,", "brn,104,7.0,0,", "plc,88,5.5,0,", "ltz,92,6.0,0,"])
JARVIS_SUGGESTIONS = ['"Give me a situation briefing"', '"Do I need more people?"', '"When will Riverview be restored?"', '"What if it becomes a Cat 4?"']


def demo_track(impact, now) -> tuple[list[dict], tuple[float, float]]:
    """The demo storm's track (and its current position) around the impact time."""
    track = [{"lat": p[0], "lng": p[1], "at": (impact + timedelta(hours=h)).isoformat(), "observed": impact + timedelta(hours=h) <= now}
             for p, h in zip(TRACK, TRACK_H)]
    return track, (TRACK[1][0], TRACK[1][1])


def comms_templates(e, now, site: str) -> list[tuple]:
    """(channel, audience, subject, body, status, ai, hours ago created, extra). The first 12 are the initial campaign; the rest
    are spare wording the demo top-up draws on."""
    landfall = e.landfall_at or now + timedelta(hours=48)
    later = max(now + timedelta(hours=2), landfall - timedelta(hours=6))  # still ahead of us, before landfall
    name = e.name
    return [
        ("sms", "all", "", f"Bayview Power & Water: {name} is forecast to bring hurricane-force winds to Hillsborough County. Charge phones, "
         f"stock water and medicine, and secure outdoor items. Report outages at {site} or text OUT to 78900.", "sent", True, 31, {}),
        ("email", "all", f"Prepare now: {name} is heading for Tampa Bay",
         f"{name} is expected to bring damaging winds and storm surge to our service area.\n\nHow to prepare:\n• Charge phones and backup batteries\n"
         f"• Keep a 3-day supply of water, food and medicine\n• Never use a generator indoors\n• Stay 35 ft from downed lines and report them on 911\n\n"
         f"We have crews and mutual-aid partners staged and will restore power as soon as it is safe. Track outages at {site}.", "sent", True, 30, {}),
        ("x", "all", "", f"{name} update: crews and mutual-aid partners are staged across Hillsborough County. Prepare now: charge devices, "
         f"stock water, secure outdoor items. Report outages at {site} #KyleTampa", "sent", True, 28, {}),
        ("facebook", "all", "", f"⚠️ {name} is on the way. Our line crews, tree crews and partner utilities are pre-staged so we can start "
         f"restoring power as soon as winds drop below 35 mph. Get ready now and bookmark {site} for live outage maps and restoration times.",
         "sent", True, 28, {}),
        ("sms", "medical", "", "Bayview Power & Water: you are registered as medical-needs/life-support. Power may be out for several days after "
         f"{name}. Arrange a backup power source or a stay at a special-needs shelter now. Questions: 1-800-555-0142.", "sent", False, 22, {}),
        ("sms", "coastal", "", f"Bayview Power & Water: storm surge from {name} may flood coastal zones. Follow county evacuation orders. We will "
         "de-energize flooded equipment for safety and restore it once water recedes.", "sent", True, 9, {}),
        ("x", "all", "", f"Our crews are pre-staged at 4 yards across the county ahead of {name}. Expect outages to start as the outer bands "
         f"arrive. Track restoration live at {site}", "pending", True, 0.7, {}),
        ("sms", "zone:brn", "", f"Bayview Power & Water: crews are staged in Brandon ahead of {name}. If your power goes out, text OUT to 78900 — "
         "smart meters will usually report it before you do.", "pending", True, 0.4, {}),
        ("sms", "all", "", f"Bayview Power & Water: {name} landfall is expected within hours. Stay indoors, keep away from downed lines and "
         f"track outages at {site}.", "scheduled", True, 3, {"scheduled_for": later}),
        ("email", "water", "Precautionary boil-water guidance", "If water pressure drops in your area after the storm, boil water for 1 minute "
         "before drinking or cooking until we confirm it is safe. We will text you when the advisory is lifted.", "scheduled", False, 5,
         {"scheduled_for": later + timedelta(hours=1)}),
        ("website", "all", "Storm center", f"{name}: crews staged, live outage map and restoration times at {site}. Updated every 30 minutes "
         "once outages begin.", "draft", True, 1.5, {}),
        ("facebook", "coastal", "", f"Coastal customers: {name} may push storm surge into Apollo Beach, Ruskin and Town 'n' Country. Please "
         "prepare to leave if ordered.", "rejected", True, 6, {"reject_reason": "Add shelter locations and the county evacuation-zone map link."}),
        # ---- spare wording for the demo top-up
        ("facebook", "all", "", f"Line crews from Georgia and the Carolinas have arrived to help with {name}. If you see a downed line, stay "
         f"35 ft away and call 911. Outage map: {site}", "pending", True, 0.5, {}),
        ("sms", "zone:rvv", "", f"Bayview Power & Water: tree crews are clearing lines in Riverview ahead of {name}. Expect short planned "
         "interruptions this afternoon.", "pending", True, 0.3, {}),
        ("email", "medical", "Your storm plan: medical-needs customers", f"Ahead of {name}, please confirm your backup power plan. Special-needs "
         "shelters open at 8 AM tomorrow. Call 1-800-555-0142 if you need transport.", "pending", False, 0.6, {}),
        ("x", "all", "", f"{name}: we will post restoration times by neighbourhood as soon as damage assessment starts. Follow along at {site}",
         "scheduled", True, 1, {"scheduled_for": later + timedelta(minutes=30)}),
        ("sms", "coastal", "", f"Bayview Power & Water: if you evacuated ahead of {name}, do not return until officials say roads are safe. We "
         "will restore flooded areas only after equipment is inspected.", "scheduled", True, 2, {"scheduled_for": later + timedelta(hours=2)}),
        ("email", "all", f"{name}: what to expect after landfall", f"Restoration happens in a set order: hospitals and water plants, then main "
         f"lines, then neighbourhoods. Check {site} for your area's estimated restoration time.", "draft", True, 0.8, {}),
        ("x", "all", "", f"Power out because of {name}? Text OUT to 78900 — no need to call.", "rejected", True, 2,
         {"reject_reason": "Mention that smart meters report most outages automatically."}),
    ]
