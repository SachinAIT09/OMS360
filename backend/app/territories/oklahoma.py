"""Territory: the demo utility "Prairie Sky Power" (fictional), an electric utility serving Oklahoma statewide —
Tulsa and Green Country, the Oklahoma City metro, the southwest plains, northwest and southeast Oklahoma.
Hazard: tornadoes (plus severe thunderstorms, ice storms and flash flooding). Zone coordinates are real town locations;
the utility, its facilities and customer counts are illustrative."""
from datetime import timedelta

from .common import path_track

KEY = "oklahoma"
HAZARD = "tornado"

# ---------------------------------------------------------------- brand
UTILITY_NAME = "Prairie Sky Power"
UTILITY_SHORT = "Prairie Sky"
SITE = "prairieskypower.example/outages"
EMAIL_DOMAIN = "prairieskypower.example"
CREW_PREFIX = "PS"
AREA = "Oklahoma"
COUNTY = "Oklahoma"
STATE = "Oklahoma"
STATE_CODE = "OK"  # NWS alert area
HASHTAG_SUFFIX = "OK"
TZ_NAME = "America/Chicago"
WEATHER_POINT = {"lat": 35.4676, "lon": -97.5164}
WEATHER_LABEL = "Oklahoma City"
MAP_CENTER = [35.55, -97.0]
MAP_ZOOM = 7
HAS_WATER = False  # electric only: lift stations are critical customers, not our own water system

LANDFALL = None
PHASES = [
    {"key": "prep", "short": "T-18h", "label": "Prepare", "h": -18, "storm": 1, "status": "SPC Day-1 High Risk for central Oklahoma"},
    {"key": "pre", "short": "T-3h", "label": "Watch", "h": -3, "storm": 3, "status": "Tornado Watch in effect"},
    {"key": "impact", "short": "T-0", "label": "Touchdown", "h": 0, "storm": 4, "status": "Tornado Warning — crews sheltered"},
    {"key": "restore", "short": "T+6h", "label": "Restore", "h": 6, "storm": 5, "status": "Storms clear — damage assessment and restoration"},
    {"key": "recover", "short": "T+72h", "label": "Recover", "h": 72, "storm": 6, "status": "Rebuild of destroyed circuits & after-action"},
]

# coastal is always False here (no surge); vuln = overhead exposure + tree canopy + age of the distribution plant
ZONES = [
    # Northeast — Tulsa and Green Country
    {"id": "tul", "code": "TUL", "name": "Tulsa", "short": "Tulsa", "lat": 36.1540, "lng": -95.9928, "cust": 205000, "vuln": 0.75, "crit": True},
    {"id": "bka", "code": "BKA", "name": "Broken Arrow", "short": "Broken Arrow", "lat": 36.0526, "lng": -95.7908, "cust": 52000, "vuln": 0.70, "crit": True},
    {"id": "owa", "code": "OWA", "name": "Owasso", "short": "Owasso", "lat": 36.2695, "lng": -95.8547, "cust": 28000, "vuln": 0.62},
    {"id": "ssp", "code": "SSP", "name": "Sand Springs", "short": "Sand Springs", "lat": 36.1398, "lng": -96.1089, "cust": 16000, "vuln": 0.78},
    {"id": "jbx", "code": "JBX", "name": "Jenks / Bixby", "short": "Jenks / Bixby", "lat": 35.9700, "lng": -95.9300, "cust": 31000, "vuln": 0.65},
    {"id": "clm", "code": "CLM", "name": "Claremore", "short": "Claremore", "lat": 36.3126, "lng": -95.6161, "cust": 16000, "vuln": 0.68},
    {"id": "bvl", "code": "BVL", "name": "Bartlesville", "short": "Bartlesville", "lat": 36.7473, "lng": -95.9808, "cust": 21000, "vuln": 0.66, "crit": True},
    # Central — Oklahoma City metro
    {"id": "okc", "code": "OKC", "name": "Oklahoma City", "short": "Oklahoma City", "lat": 35.4676, "lng": -97.5164, "cust": 228000, "vuln": 0.74, "crit": True},
    {"id": "moo", "code": "MOO", "name": "Moore", "short": "Moore", "lat": 35.3395, "lng": -97.4867, "cust": 31000, "vuln": 0.85},
    {"id": "nor", "code": "NOR", "name": "Norman", "short": "Norman", "lat": 35.2226, "lng": -97.4395, "cust": 61000, "vuln": 0.70, "crit": True},
    {"id": "edm", "code": "EDM", "name": "Edmond", "short": "Edmond", "lat": 35.6528, "lng": -97.4781, "cust": 48000, "vuln": 0.58},
    {"id": "mwc", "code": "MWC", "name": "Midwest City / Del City", "short": "Midwest City", "lat": 35.4495, "lng": -97.3967, "cust": 36000, "vuln": 0.82, "med": True},
    {"id": "chk", "code": "CHK", "name": "Chickasha", "short": "Chickasha", "lat": 35.0526, "lng": -97.9364, "cust": 10000, "vuln": 0.80},
    # Southwest
    {"id": "law", "code": "LAW", "name": "Lawton", "short": "Lawton", "lat": 34.6036, "lng": -98.3959, "cust": 50000, "vuln": 0.72, "crit": True},
    {"id": "dun", "code": "DUN", "name": "Duncan", "short": "Duncan", "lat": 34.5023, "lng": -97.9578, "cust": 12000, "vuln": 0.68},
    {"id": "alt", "code": "ALT", "name": "Altus", "short": "Altus", "lat": 34.6381, "lng": -99.3340, "cust": 9000, "vuln": 0.64},
    # Northwest
    {"id": "end", "code": "END", "name": "Enid", "short": "Enid", "lat": 36.3956, "lng": -97.8784, "cust": 26000, "vuln": 0.66, "crit": True},
    {"id": "wwd", "code": "WWD", "name": "Woodward", "short": "Woodward", "lat": 36.4337, "lng": -99.3904, "cust": 7000, "vuln": 0.62},
    # Southeast
    {"id": "msk", "code": "MSK", "name": "Muskogee", "short": "Muskogee", "lat": 35.7479, "lng": -95.3697, "cust": 21000, "vuln": 0.74, "crit": True},
    {"id": "mca", "code": "MCA", "name": "McAlester", "short": "McAlester", "lat": 34.9334, "lng": -95.7697, "cust": 11000, "vuln": 0.70},
]
for _z in ZONES:
    _z["water"] = 0

REGIONS = [
    {"id": "northeast", "name": "Northeast", "zones": ["tul", "bka", "owa", "ssp", "jbx", "clm", "bvl"]},
    {"id": "central", "name": "Central", "zones": ["okc", "moo", "nor", "edm", "mwc", "chk"]},
    {"id": "southwest", "name": "Southwest", "zones": ["law", "dun", "alt"]},
    {"id": "northwest", "name": "Northwest", "zones": ["end", "wwd"]},
    {"id": "southeast", "name": "Southeast", "zones": ["msk", "mca"]},
]

FACILITIES = [
    {"name": "Green Country Medical Center", "t": "H", "type": "Hospital", "lat": 36.1300, "lng": -95.9700, "zone": "tul", "feeder": "FDR-TUL-01", "backup": "96 h diesel"},
    {"name": "Central Oklahoma Medical Center", "t": "H", "type": "Hospital", "lat": 35.4800, "lng": -97.4980, "zone": "okc", "feeder": "FDR-OKC-02", "backup": "96 h diesel"},
    {"name": "Moore Community Hospital", "t": "H", "type": "Hospital", "lat": 35.3290, "lng": -97.4900, "zone": "moo", "feeder": "FDR-MOO-02", "backup": "48 h diesel"},
    {"name": "Cleveland County Medical Center", "t": "H", "type": "Hospital", "lat": 35.2300, "lng": -97.4300, "zone": "nor", "feeder": "FDR-NOR-01", "backup": "72 h diesel"},
    {"name": "Southwest Plains Hospital", "t": "H", "type": "Hospital", "lat": 34.6100, "lng": -98.4100, "zone": "law", "feeder": "FDR-LAW-01", "backup": "72 h diesel"},
    {"name": "Broken Arrow Regional Hospital", "t": "H", "type": "Hospital", "lat": 36.0400, "lng": -95.8000, "zone": "bka", "feeder": "FDR-BKA-03", "backup": "48 h diesel"},
    {"name": "OKC North Water Treatment Plant", "t": "W", "type": "Water plant", "lat": 35.5700, "lng": -97.5800, "zone": "okc", "feeder": "FDR-OKC-05", "backup": "Dual feed + 3 MW gen"},
    {"name": "Tulsa East Water Treatment Plant", "t": "W", "type": "Water plant", "lat": 36.1900, "lng": -95.8800, "zone": "tul", "feeder": "FDR-TUL-04", "backup": "Dual feed"},
    {"name": "Oklahoma County Emergency Operations Ctr", "t": "E", "type": "EOC", "lat": 35.4700, "lng": -97.5200, "zone": "okc", "feeder": "FDR-OKC-03", "backup": "Dual feed"},
    {"name": "Tulsa Area Emergency Management", "t": "E", "type": "EOC", "lat": 36.1600, "lng": -95.9900, "zone": "tul", "feeder": "FDR-TUL-02", "backup": "Dual feed"},
    {"name": "Storm shelter — Moore High School", "t": "S", "type": "Shelter", "lat": 35.3400, "lng": -97.4700, "zone": "moo", "feeder": "FDR-MOO-04", "backup": "None — portable gen"},
    {"name": "Storm shelter — Chickasha Event Center", "t": "S", "type": "Shelter", "lat": 35.0400, "lng": -97.9400, "zone": "chk", "feeder": "FDR-CHK-01", "backup": "None — portable gen"},
    {"name": "Midwest City medical-needs cluster", "t": "M", "type": "Medical-needs", "lat": 35.4500, "lng": -97.3900, "zone": "mwc", "feeder": "FDR-MWC-01", "backup": "Mixed"},
]

YARDS = [
    {"name": "State Fairgrounds staging (OKC)", "lat": 35.4766, "lng": -97.5683, "cap": 650},
    {"name": "Expo Square staging (Tulsa)", "lat": 36.1339, "lng": -95.9300, "cap": 500},
    {"name": "Norman Service Center", "lat": 35.2000, "lng": -97.4800, "cap": 260},
    {"name": "Lawton Service Center", "lat": 34.6200, "lng": -98.4200, "cap": 200},
    {"name": "Muskogee Operations Yard", "lat": 35.7600, "lng": -95.4000, "cap": 180},
]

SAMPLE_ADDRESSES = [
    ("1200 S Boston Ave, Tulsa", "tul"),
    ("2100 N Aspen Ave, Broken Arrow", "bka"),
    ("400 SW 4th St, Moore", "moo"),
    ("1500 W Main St, Norman", "nor"),
    ("700 N Broadway Ave, Oklahoma City", "okc"),
    ("2200 NW Cache Rd, Lawton", "law"),
]

# ---------------------------------------------------------------- partners
MA_PARTNERS = [("Lone Star Grid Services", "Texas", 0.4), ("Ozark Line Constructors", "Arkansas", 0.35),
               ("Heartland Power Alliance", "Kansas", 0.25)]
TREE_PARTNER = ("Red River Vegetation", "Texas")
DA_PARTNER = ("Plains Damage Assessment", "Missouri")
HISTORY_MA = [("Lone Star Grid Services", "Texas", 90), ("Ozark Line Constructors", "Arkansas", 60)]

# ---------------------------------------------------------------- demo scenario: a central Oklahoma tornado outbreak
# Each path: EF rating, damage width and its points; the second, weaker tornado touches down near Jenks hours later.
TORNADO_PATHS = [
    {"ef": 4, "width_m": 1300, "start_h": 0.0, "mph": 32,
     "points": [[35.080, -97.920], [35.180, -97.720], [35.260, -97.585], [35.330, -97.490], [35.395, -97.420], [35.440, -97.355]]},
    {"ef": 2, "width_m": 450, "start_h": 4.0, "mph": 40,
     "points": [[35.950, -95.975], [36.000, -95.870], [36.050, -95.780], [36.095, -95.700]]},
]
DEMO_EVENT = {"name": "Central Oklahoma Tornado Outbreak", "kind": "Tornado", "category": 4, "max_wind_mph": 175, "pressure_mb": 992,
              "movement": "NE at 32 mph", "hours_out": 8,
              "notes": "SPC Day-1 High Risk. Supercells forecast to form along the dryline west of I-44 by mid-afternoon; a long-track "
                       "EF4 is the planning case through Chickasha, Newcastle, Moore and Midwest City, with a second supercell near Tulsa "
                       "this evening."}
NEW_EVENT = {"kind": "Tornado", "lat": 35.30, "lng": -97.55}
HISTORY_POSITION = (35.47, -97.52)
HISTORICAL = [
    {"name": "May Hail & Wind Event", "kind": "Severe Thunderstorm", "category": 2, "days_ago": 160, "actual": 1.06},
    {"name": "Norman–Moore Tornado", "kind": "Tornado", "category": 3, "days_ago": 420, "actual": 0.94,
     "paths": [{"ef": 3, "width_m": 800, "start_h": 0, "mph": 30, "points": [[35.180, -97.520], [35.260, -97.450], [35.330, -97.400]]}]},
    {"name": "Green Country Flash Flood", "category": 1, "days_ago": 75, "actual": 1.03, "rng": 7,
     "rain": {"rain_total_in": 6.0, "rain_rate_in_hr": 2.2, "duration_h": 10, "soil_saturation": 0.7}},
]
RAIN_DEMO = {"name": "Tulsa Flash Flood Event", "lat": 36.15, "lng": -95.99, "worst": ["Sand Springs", "Jenks / Bixby"],
             "notes": "Training thunderstorms over northeast Oklahoma. 4–7 in observed, locally 9 in near Sand Springs and Jenks; "
                      "low-water crossings closed along the Arkansas River."}
RAIN_GRADIENT = {"ref_lat": 35.6, "spread": 0.6, "sign": 1}  # training storms over Green Country (north of ref_lat)
SAMPLE_FORECAST_CSV = "zone,gust_mph,rain_in,surge_ft,arrival_at\n" + "\n".join([
    "moo,165,2.5,0,", "mwc,140,2.0,0,", "chk,150,2.0,0,", "nor,95,2.5,0,", "okc,85,2.0,0,", "jbx,120,1.5,0,", "bka,115,1.5,0,"])
JARVIS_SUGGESTIONS = ['"Give me a situation briefing"', '"Which circuits are in the tornado path?"', '"When will Moore be restored?"',
                      '"Oldest transformers in the Central region"']


def demo_track(impact, now) -> tuple[list[dict], tuple[float, float]]:
    return path_track(TORNADO_PATHS, impact, now), (TORNADO_PATHS[0]["points"][0][0], TORNADO_PATHS[0]["points"][0][1])


def comms_templates(e, now, site: str) -> list[tuple]:
    """(channel, audience, subject, body, status, ai, hours ago created, extra) — the tornado-day campaign. The first 12 are the
    initial campaign; the rest are spare wording the demo top-up draws on."""
    touchdown = e.landfall_at or now + timedelta(hours=8)
    later = max(now + timedelta(hours=1), touchdown - timedelta(hours=2))  # still ahead of us, before the storms fire
    name = e.name
    return [
        ("sms", "all", "", f"Prairie Sky Power: the Storm Prediction Center has issued a High Risk for central Oklahoma today. Know your shelter, "
         f"charge phones and keep shoes and a flashlight by your safe room. Report outages at {site} or text OUT to 78900.", "sent", True, 20, {}),
        ("email", "all", f"Severe weather today: be ready to shelter",
         f"Long-track tornadoes are possible across central Oklahoma this afternoon and evening.\n\nHow to prepare:\n• Know where you will shelter "
         f"and practise getting there\n• Charge phones and backup batteries\n• Keep shoes, a helmet and a flashlight in your safe room\n"
         f"• After the storm, stay 35 ft from downed lines and report them on 911\n\nOur line crews are staged outside the risk area and will move "
         f"in as soon as the storms pass. Track outages at {site}.", "sent", True, 19, {}),
        ("x", "all", "", f"High Risk for severe storms in central OK today. Our crews and partners from Texas, Arkansas and Kansas are staged and "
         f"ready to move in once the storms pass. Know your shelter. Outage map: {site} #okwx", "sent", True, 18, {}),
        ("facebook", "all", "", f"⚠️ Tornadoes are possible across central Oklahoma this afternoon. Our crews are staged at the State Fairgrounds, "
         f"Norman and Lawton, outside the highest-risk area, so they can start restoring power as soon as it's safe. Bookmark {site} for live "
         "outage maps and restoration times.", "sent", True, 17, {}),
        ("sms", "medical", "", "Prairie Sky Power: you are registered as medical-needs/life-support. Severe storms today could cause outages "
         "lasting several days where tornadoes strike. Charge backup batteries and plan where you will go. Questions: 1-800-555-0142.", "sent", False, 14, {}),
        ("sms", "zone:moo", "", f"Prairie Sky Power: Moore is in today's highest-risk area. If a warning is issued, shelter immediately. After "
         "the storm, never touch downed lines — assume they are live.", "sent", True, 6, {}),
        ("x", "all", "", f"Our crews are staged at 5 yards outside the tornado watch area. Expect outages from hail and straight-line winds too. "
         f"Track restoration live at {site}", "pending", True, 0.7, {}),
        ("sms", "zone:nor", "", f"Prairie Sky Power: crews are staged in Norman ahead of today's storms. If your power goes out, text OUT to 78900 — "
         "smart meters will usually report it before you do.", "pending", True, 0.4, {}),
        ("sms", "all", "", f"Prairie Sky Power: a Tornado Watch is in effect. When a warning is issued for your area, go to your shelter now. "
         f"Track outages at {site}.", "scheduled", True, 3, {"scheduled_for": later}),
        ("email", "medical", "If the tornado damages your home", "If your meter base or service mast is damaged, an electrician must repair it "
         "before we can reconnect you. Call 1-800-555-0142 and we will prioritise medical-needs customers.", "scheduled", False, 5,
         {"scheduled_for": later + timedelta(hours=1)}),
        ("website", "all", "Storm center", f"{name}: crews staged, live outage map and restoration times at {site}. Updated every 30 minutes "
         "once outages begin.", "draft", True, 1.5, {}),
        ("facebook", "zone:mwc", "", f"Midwest City and Del City: today's storms may bring tornadoes and large hail. Please make sure your "
         "family knows where to shelter.", "rejected", True, 6, {"reject_reason": "Add the public storm shelter list and the city siren schedule."}),
        # ---- spare wording for the demo top-up
        ("facebook", "all", "", f"Line crews from Texas, Arkansas and Kansas are rolling in to help after {name}. If you see a downed line, stay "
         f"35 ft away and call 911. Outage map: {site}", "pending", True, 0.5, {}),
        ("sms", "zone:chk", "", f"Prairie Sky Power: tree crews are working in Chickasha ahead of today's storms. Expect short planned "
         "interruptions this afternoon.", "pending", True, 0.3, {}),
        ("email", "medical", "Your storm plan: medical-needs customers", f"Ahead of {name}, please confirm your backup power plan. "
         "Call 1-800-555-0142 if you need help getting to a shelter.", "pending", False, 0.6, {}),
        ("x", "all", "", f"{name}: we will post restoration times by neighbourhood and circuit as soon as damage assessment starts. Follow along "
         f"at {site}", "scheduled", True, 1, {"scheduled_for": later + timedelta(minutes=30)}),
        ("sms", "zone:moo", "", "Prairie Sky Power: if the tornado damaged your home, do not return until officials say it is safe. Homes with a "
         "damaged meter base need an electrician before we can reconnect.", "scheduled", True, 2, {"scheduled_for": later + timedelta(hours=2)}),
        ("email", "all", f"{name}: what to expect after the storms", "Restoration happens in a set order: hospitals and water plants, then main "
         f"lines, then neighbourhoods. Circuits in the tornado's direct path need rebuilding and take longest. Check {site} for your circuit's "
         "estimated restoration time.", "draft", True, 0.8, {}),
        ("x", "all", "", f"Power out because of {name}? Text OUT to 78900 — no need to call.", "rejected", True, 2,
         {"reject_reason": "Mention that smart meters report most outages automatically."}),
    ]
