"""First-run data: Bayview Power & Water network, roster, users, two closed historical storms and
the current planning event. Deterministic (seeded RNG) so every install looks the same."""
import random
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .auth import hash_password
from .data import FACILITIES, TRACK, TRACK_H, YARDS, ZONES
from .db import set_setting
from .models import (AuditLog, Crew, Facility, Feeder, Message, MutualAidRequest, NotificationRule, Outage, OutageEvent, PredictionRun,
                     PublishedEtr, Recommendation, StagingYard, StormEvent, User, Zone, utcnow)
from .services import ops

USERS = [
    ("marcus.reed@bayviewpw.example", "Marcus Reed", "Chief Executive Officer", "executive"),
    ("dana.whitaker@bayviewpw.example", "Dana Whitaker", "VP, Storm Operations", "ops_manager"),
    ("luis.ortega@bayviewpw.example", "Luis Ortega", "Distribution Dispatcher", "dispatcher"),
    ("priya.nair@bayviewpw.example", "Priya Nair", "Director, Customer Communications", "comms"),
    ("admin@bayviewpw.example", "Sam Patel", "Systems Administrator", "admin"),
]
DEFAULT_PASSWORD = "oms360"
FIRST = ["James", "Maria", "Robert", "Linda", "Carlos", "Angela", "Derek", "Tanya", "Kevin", "Rosa", "Brian", "Monique", "Travis",
         "Keisha", "Hector", "Wendy", "Andre", "Lauren", "Victor", "Nina"]
LAST = ["Johnson", "Alvarez", "Smith", "Nguyen", "Brooks", "Rivera", "Coleman", "Price", "Diaz", "Howard", "Morales", "Bennett",
        "Reyes", "Foster", "Ramirez", "Hughes", "Castillo", "Graham", "Ortiz", "Wallace"]
RULES = [
    ("Outage detected by smart meter → SMS within 5 min", "outage_detected", "sms", True),
    ("AI ETR changes by more than 1 hour → SMS + website", "etr_changed", "sms", True),
    ("Crew dispatched to your area → SMS", "crew_dispatched", "sms", True),
    ('Power restored → "Still out? Reply OUT" SMS', "restored", "sms", True),
    ("Boil-water advisory issued → SMS + IVR to affected water customers", "boil_water", "sms", True),
    ("Auto-publish social posts without human approval", "social_autopublish", "x", False),
]


def seed_if_empty(s: Session) -> None:
    if s.scalars(select(User)).first():
        return
    rng = random.Random(360)
    now = utcnow()

    # ---- network
    for z in ZONES:
        s.add(Zone(id=z["id"], code=z["code"], name=z["name"], short=z["short"], lat=z["lat"], lng=z["lng"], customers=z["cust"],
                   water_customers=z["water"], vulnerability=z["vuln"], coastal=z["coastal"], critical=z["crit"], medical=z["med"]))
    s.flush()
    for z in ZONES:
        n = max(6, z["cust"] // 6000)
        for i in range(n):
            s.add(Feeder(id=f"FDR-{z['code']}-{i + 1:02d}", zone_id=z["id"], customers=int(z["cust"] / n * rng.uniform(0.7, 1.3)),
                         overhead_pct=rng.randint(35, 95) if z["vuln"] > 0.6 else rng.randint(15, 60), last_trimmed=rng.randint(2019, 2025)))
    for f in FACILITIES:
        s.add(Facility(name=f["name"], kind=f["t"], type=f["type"], lat=f["lat"], lng=f["lng"], zone_id=f["zone"], feeder_id=f["feeder"], backup=f["backup"]))
    for y in YARDS:
        s.add(StagingYard(name=y["name"], lat=y["lat"], lng=y["lng"], capacity=y["cap"]))
    s.flush()

    # ---- people
    for email, name, title, role in USERS:
        s.add(User(email=email, name=name, title=title, role=role, password_hash=hash_password(DEFAULT_PASSWORD)))
    zones = s.scalars(select(Zone)).all()
    for kind, count, size, prefix in (("line", 160, 4, "L"), ("tree", 45, 4, "T"), ("assessment", 20, 2, "A")):
        for i in range(count):
            z = zones[i % len(zones)]
            s.add(Crew(code=f"BV-{prefix}-{i + 1:03d}", kind=kind, company="Bayview Power & Water", source="internal", size=size,
                       lead=f"{rng.choice(FIRST)} {rng.choice(LAST)}", lat=z.lat + rng.uniform(-0.03, 0.03), lng=z.lng + rng.uniform(-0.03, 0.03)))
    for name, trigger, channel, on in RULES:
        s.add(NotificationRule(name=name, trigger=trigger, channel=channel, enabled=on))
    set_setting(s, "connector_mode", "sandbox")
    s.flush()

    # ---- history
    _historical(s, rng, "Hurricane Delphine", 2, now - timedelta(days=390), 0.93)
    _historical(s, rng, "Hurricane Barrett", 1, now - timedelta(days=118), 1.08)
    # own generator, so adding it leaves the rest of the seeded demo unchanged
    _historical(s, random.Random(7), "June Rain Event", 1, now - timedelta(days=60), 1.04,
                rain={"rain_total_in": 7.5, "rain_rate_in_hr": 1.8, "duration_h": 18, "soil_saturation": 0.8})

    # ---- current planning event: Hurricane Kyle, landfall ~72 h out
    landfall = (now + timedelta(hours=72)).replace(minute=0, second=0, microsecond=0)
    track = [{"lat": p[0], "lng": p[1], "at": (landfall + timedelta(hours=h)).isoformat(), "observed": landfall + timedelta(hours=h) <= now}
             for p, h in zip(TRACK, TRACK_H)]
    dana = s.scalars(select(User).where(User.role == "ops_manager")).first()
    kyle = StormEvent(name="Hurricane Kyle", kind="Hurricane", source="manual", status="preparing", category=3, max_wind_mph=105,
                      pressure_mb=968, lat=TRACK[1][0], lng=TRACK[1][1], movement="NNE at 12 mph", landfall_at=landfall, track=track,
                      notes="Forecast landfall near the mouth of Tampa Bay. Planning scenario based on the latest advisory package.",
                      created_by=dana.id, created_at=now - timedelta(hours=6))
    s.add(kyle)
    s.flush()
    from .services.prediction import predict
    res = predict(s, kyle)
    s.add(PredictionRun(event_id=kyle.id, category=3, result=res, created_by=dana.id, created_at=now - timedelta(hours=2)))
    s.add(AuditLog(at=now - timedelta(hours=6), user_name=dana.name, action="event.created", entity="storm_event", entity_id=str(kyle.id),
                   detail="Hurricane Kyle created (Monitoring)", event_id=kyle.id))
    s.add(AuditLog(at=now - timedelta(hours=3), user_name=dana.name, action="event.status", entity="storm_event", entity_id=str(kyle.id),
                   detail="Hurricane Kyle: Monitoring → Preparing", event_id=kyle.id))
    s.add(AuditLog(at=now - timedelta(hours=2), user_name=dana.name, action="prediction.run", entity="storm_event", entity_id=str(kyle.id),
                   detail=f"Cat 3 prediction: {res['pred_total']:,} customers", event_id=kyle.id))
    _early_bands(s, rng, kyle, now)
    _pre_storm_comms(s, kyle, now)
    s.commit()


def ensure_demo_activity(s: Session) -> None:
    """Databases seeded before this demo activity existed: give the demo storm its pre-landfall outages and comms once."""
    kyle = _demo_storm(s)
    if not kyle:
        return
    if not s.scalars(select(Outage.id).where(Outage.event_id == kyle.id)).first():
        _early_bands(s, random.Random(361), kyle, utcnow())
    if not s.scalars(select(Message.id).where(Message.event_id == kyle.id)).first():
        _pre_storm_comms(s, kyle, utcnow())
    s.commit()


def _demo_storm(s: Session) -> StormEvent | None:
    return s.scalars(select(StormEvent).where(StormEvent.name == "Hurricane Kyle", StormEvent.source == "manual",
                                              StormEvent.status == "preparing")).first()


# Demo floor that every app load restores (sandbox mode only): open work on the storm and messages in each workflow state.
DEMO_OPEN_FLOOR = 12
DEMO_MESSAGE_FLOOR = {"pending": 2, "scheduled": 2, "draft": 1, "rejected": 1}
TOPUP_STATUS = [("in_progress", 4), ("assigned", 4), ("assessed", 3), ("reported", 5)]


def refresh_demo(s: Session) -> dict:
    """Top the demo storm back up to its floor without undoing anything the user did: fill only what's missing."""
    rain_outages = _refresh_rain_demo(s)
    e = _demo_storm(s)
    if not e:
        return {"outages": rain_outages, "messages": 0}
    now = utcnow()
    open_n = s.scalar(select(func.count(Outage.id)).where(Outage.event_id == e.id,
                                                         Outage.status.in_(["reported", "assessed", "assigned", "in_progress"]))) or 0
    outages = _early_bands(s, random.Random(), e, now, TOPUP_STATUS, recent=True) if open_n < DEMO_OPEN_FLOOR else 0
    from .services import comms
    aud = {a["id"]: a["count"] for a in comms.audiences(s)}
    rows = s.execute(select(Message.status, Message.body).where(Message.event_id == e.id)).all()
    used = {body for _, body in rows}
    have: dict[str, int] = {}
    for st, _ in rows:
        have[st] = have.get(st, 0) + 1
    rng = random.Random()
    messages = 0
    for status, floor in DEMO_MESSAGE_FLOOR.items():
        pool = [t for t in _comms_templates(e, now) if t[4] == status]
        fresh = [t for t in pool if t[3] not in used] or pool  # prefer wording that isn't on screen already
        for t in fresh[:max(0, floor - have.get(status, 0))]:
            _add_message(s, e, aud, (*t[:6], rng.uniform(0.1, 1.2), t[7]), now)
            messages += 1
    s.flush()
    return {"outages": outages + rain_outages, "messages": messages}


# ---------------------------------------------------------------- demo: Rain Event in restoration (circuit / region ETRs)
RAIN_DEMO = "Tampa Bay Rain Event"
RAIN_DEMO_STATUS = [("restored", 55), ("in_progress", 16), ("assigned", 18), ("assessed", 24), ("reported", 20)]
RAIN_OPEN_FLOOR = 25


def _rain_demo(s: Session) -> StormEvent | None:
    return s.scalars(select(StormEvent).where(StormEvent.name == RAIN_DEMO, StormEvent.status.in_(["active", "restoring"]))).first()


def ensure_rain_demo(s: Session) -> None:
    """A rain event already in restoration, so region and circuit ETRs have live data to show: tickets across every
    circuit state, a few manual ETRs, the most certain circuits published, Flood Watch messages sent.
    Added once to new and existing databases; created before the demo hurricane so that stays the current event."""
    from .services import comms
    from .services.events import RAIN
    from .services.prediction import predict
    if s.scalars(select(StormEvent.id).where(StormEvent.name == RAIN_DEMO)).first():
        return
    from .services import notify
    notify.ensure_rule(s)  # publishing below texts the customers on each circuit
    rng = random.Random(4242)
    now = utcnow()
    onset = (now - timedelta(hours=16)).replace(minute=0, second=0, microsecond=0)
    dana = s.scalars(select(User).where(User.role == "ops_manager")).first()
    e = StormEvent(name=RAIN_DEMO, kind=RAIN, source="manual", status="restoring", category=1, max_wind_mph=35, pressure_mb=1006,
                   lat=27.95, lng=-82.46, movement="", landfall_at=onset, track=[], rain_total_in=6.5, rain_rate_in_hr=1.8,
                   duration_h=14, soil_saturation=0.75, created_by=dana.id if dana else None,
                   notes="Stalled frontal boundary over Tampa Bay. 5–8 in observed, locally 10 in along the South Shore; streets flooded in Ruskin and Apollo Beach.",
                   created_at=onset - timedelta(days=2), activated_at=onset - timedelta(hours=1), restoring_at=onset + timedelta(hours=12))
    s.add(e)
    s.flush()
    res = predict(s, e)
    s.add(PredictionRun(event_id=e.id, category=1, result=res, created_by=dana.id if dana else None, created_at=onset - timedelta(hours=20)))
    _early_bands(s, rng, e, now, RAIN_DEMO_STATUS)
    # a dispatcher pinned some ETRs by hand after talking to the crews
    for o in s.scalars(select(Outage).where(Outage.event_id == e.id, Outage.status == "assessed").limit(5)).all():
        o.etr_override, o.etr_at = True, now + timedelta(hours=rng.uniform(2, 7))
        _ev(s, o, "etr", "ETR set manually after crew assessment", "Luis Ortega", now - timedelta(minutes=rng.uniform(5, 50)))
    s.flush()
    zones = {o.zone_id for o in s.scalars(select(Outage).where(Outage.event_id == e.id, Outage.status.in_(ops.OPEN))).all()}
    for z in sorted(zones)[:4]:
        s.add(PublishedEtr(event_id=e.id, zone_id=z, published_by="Dana Whitaker", published_at=now - timedelta(hours=3)))
    from .routers.field import publish_circuits
    publish_circuits(s, e, "Dana Whitaker")  # circuits at ≥80% confidence
    aud = {a["id"]: a["count"] for a in comms.audiences(s)}
    for ch, audience, purpose, hours in (("sms", "flood", "warning", 26), ("x", "all", "prepare", 30), ("sms", "out", "outage", 10),
                                         ("x", "all", "etr", 2)):
        d = comms.draft(e, ch, purpose, {"customers_out": 9000, "restored_pct": 0.55, "line_workers": 640, "worst": ["Ruskin", "Apollo Beach"]})
        _add_message(s, e, aud, (ch, audience, d["subject"], d["body"], "sent", True, hours, {}), now)
    for at, action, detail in ((e.created_at, "event.created", f"{RAIN_DEMO} created (Monitoring)"),
                               (e.activated_at, "event.status", f"{RAIN_DEMO}: Preparing → Active"),
                               (e.restoring_at, "event.status", f"{RAIN_DEMO}: Active → Restoring")):
        s.add(AuditLog(at=at, user_name="Dana Whitaker", action=action, entity="storm_event", entity_id=str(e.id), detail=detail, event_id=e.id))
    s.commit()


def ensure_forecast_demo(s: Session) -> None:
    """The parent company's forecast for each open demo event (mock feed) with a prediction run on it, the circuit-ETR
    text rule, and simulated publishing history so confidence calibration has something to show."""
    from .services import calibration, forecast, notify
    from .services.prediction import predict
    notify.ensure_rule(s)
    for e in (_demo_storm(s), _rain_demo(s)):
        if e and not forecast.latest_forecast(s, e.id):
            fc = forecast.save(s, e, forecast.mock_parent_forecast(s, e), forecast.PARENT_SOURCE, "Parent-company feed",
                               issued_at=utcnow() - timedelta(hours=1))
            res = predict(s, e)
            s.add(PredictionRun(event_id=e.id, category=res["category"], result=res, created_at=fc.issued_at + timedelta(minutes=5)))
            s.add(AuditLog(at=fc.issued_at, user_name="Parent-company feed", action="forecast.imported", entity="storm_event",
                           entity_id=str(e.id), detail=f"{fc.source} forecast imported; prediction re-run: {res['pred_total']:,} customers", event_id=e.id))
    calibration.ensure_history(s)
    s.commit()


def _refresh_rain_demo(s: Session) -> int:
    """Field crews in the sandbox finish work in minutes; keep the rain demo's circuits stocked with open work."""
    e = _rain_demo(s)
    if not e:
        return 0
    open_n = s.scalar(select(func.count(Outage.id)).where(Outage.event_id == e.id, Outage.status.in_(ops.OPEN))) or 0
    return _early_bands(s, random.Random(), e, utcnow(), TOPUP_STATUS, recent=True) if open_n < RAIN_OPEN_FLOOR else 0


def _comms_templates(e: StormEvent, now) -> list[tuple]:
    """(channel, audience, subject, body, status, ai, hours ago created, extra). The first 12 are the initial campaign; the rest
    are spare wording the demo top-up draws on."""
    from .services import comms
    landfall = e.landfall_at or now + timedelta(hours=48)
    later = max(now + timedelta(hours=2), landfall - timedelta(hours=6))  # still ahead of us, before landfall
    site, name = comms.SITE, e.name
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


def _add_message(s: Session, e: StormEvent, aud: dict, t: tuple, now) -> None:
    from .services import comms
    ch, audience, subject, body, status, ai, hours, extra = t
    created = now - timedelta(hours=hours)
    m = Message(event_id=e.id, channel=ch, audience=audience, subject=subject, body=body, status=status, ai_generated=ai,
                recipients=comms.recipients(ch, aud.get(audience, 0)), created_by="Priya Nair", created_at=created, updated_at=created,
                reject_reason=extra.get("reject_reason", ""), scheduled_for=extra.get("scheduled_for"))
    if status in ("sent", "scheduled"):
        m.approved_by = "Marcus Reed"
    if status == "sent":
        m.sent_at = created + timedelta(minutes=25)
    s.add(m)


def _pre_storm_comms(s: Session, e: StormEvent, now) -> None:
    """The campaign a utility runs in the days before landfall, in every workflow state, plus automated-text counts."""
    from .services import comms
    aud = {a["id"]: a["count"] for a in comms.audiences(s)}
    for t in _comms_templates(e, now)[:12]:
        _add_message(s, e, aud, t, now)
    # Automated texts the early-band tickets would already have triggered; never lowers a counter that's already higher.
    rules = {r.trigger: r for r in s.scalars(select(NotificationRule)).all()}
    tickets = s.scalars(select(Outage).where(Outage.event_id == e.id)).all()
    texted = lambda ts: round(sum(t.customers for t in ts) * 0.71)  # share of customers with a mobile number on file
    counts = {"outage_detected": texted(tickets), "etr_changed": round(texted(tickets) * 0.3),
              "crew_dispatched": texted([t for t in tickets if t.crew_id]), "restored": texted([t for t in tickets if t.status == "restored"])}
    for trigger, n in counts.items():
        if trigger in rules:
            rules[trigger].sent_count = max(rules[trigger].sent_count, n)
    s.flush()


# Pre-landfall tickets: the outer rain bands and gusts knock out scattered services days before the eye arrives.
EARLY_STATUS = [("restored", 16), ("in_progress", 7), ("assigned", 9), ("assessed", 5), ("reported", 8)]


def _early_bands(s: Session, rng: random.Random, e: StormEvent, now, mix=EARLY_STATUS, recent: bool = False) -> int:
    from .services.connector import new_ticket
    zones = s.scalars(select(Zone)).all()
    feeders: dict = {}
    for f in s.scalars(select(Feeder)).all():
        feeders.setdefault(f.zone_id, []).append(f)
    facilities = {f.feeder_id: f for f in s.scalars(select(Facility)).all()}
    crews = [c for c in s.scalars(select(Crew).where(Crew.kind == "line", Crew.source == "internal")).all() if c.status == "available"]
    rng.shuffle(crews)
    weights = [z.customers * z.vulnerability * (1.6 if z.coastal else 1) for z in zones]  # bands hit the coast first
    statuses = [st for st, n in mix for _ in range(n)]
    rng.shuffle(statuses)
    for status in statuses:
        if status not in ("reported", "assessed") and not crews:
            status = "reported"  # no free crew to put on it
        z = rng.choices(zones, weights)[0]
        reported = now - timedelta(minutes=rng.uniform(20, 90) if recent else rng.uniform(20, 9 * 60))
        o = new_ticket(s, e, z, feeders[z.id], 70, facilities, rng, at=reported)
        if e.kind != "Rain Event":
            o.cause = rng.choices(["wind", "tree", "equipment"], [45, 45, 10])[0]
        o.customers = min(o.customers, rng.randint(8, 900))
        s.execute(update(OutageEvent).where(OutageEvent.outage_id == o.id).values(at=reported))
        if status == "reported":
            continue
        if status == "assessed":
            o.status = "assessed"
            _ev(s, o, "status", "Status reported → assessed", "Field assessor", reported + timedelta(minutes=rng.uniform(10, 40)))
            continue
        crew = crews.pop()
        hours = ops.job_hours(o)
        o.crew_id, o.crew = crew.id, crew
        o.assigned_at = min(now - timedelta(minutes=5), reported + timedelta(minutes=rng.uniform(15, 75)))
        o.etr_at = o.assigned_at + timedelta(hours=ops.TRAVEL_H + hours)
        _ev(s, o, "assigned", f"Assigned to {crew.code} ({crew.company}, {crew.size} workers). Committed ETR set.", "Luis Ortega", o.assigned_at)
        if status == "assigned":
            o.status, crew.status = "assigned", "assigned"
            continue
        o.started_at = min(now - timedelta(minutes=2), o.assigned_at + timedelta(hours=ops.TRAVEL_H))
        _ev(s, o, "status", "Status assigned → in progress", f"{crew.code} (mobile app)", o.started_at)
        if status == "in_progress":
            o.status, crew.status = "in_progress", "working"
            continue
        o.status = "restored"
        o.restored_at = min(now - timedelta(minutes=1), o.started_at + timedelta(hours=hours * rng.uniform(0.6, 1.2)))
        _ev(s, o, "status", "Status in progress → restored", f"{crew.code} (mobile app)", o.restored_at)
    s.flush()
    return len(statuses)


def ensure_network_hierarchy(s: Session) -> None:
    """Regions and substations above the feeders (circuits) — added to new and existing databases."""
    from .data import REGIONS, SUBSTATION_SIDES
    from .models import Region, Substation
    zones = {z.id: z for z in s.scalars(select(Zone)).all()}
    for r in REGIONS:
        if not s.get(Region, r["id"]):
            s.add(Region(id=r["id"], name=r["name"]))
        s.flush()
        for zid in r["zones"]:
            if zid in zones and not zones[zid].region_id:
                zones[zid].region_id = r["id"]
    feeders: dict[str, list[Feeder]] = {}
    for f in s.scalars(select(Feeder).order_by(Feeder.id)).all():
        feeders.setdefault(f.zone_id, []).append(f)
    have = {sub.zone_id for sub in s.scalars(select(Substation)).all()}
    for zid, fs in feeders.items():
        if zid in have:
            continue
        z = zones[zid]
        n = min(4, max(2, -(-len(fs) // 8)))
        subs = []
        for i, (side, dlat, dlng) in enumerate(SUBSTATION_SIDES[:n]):
            subs.append(Substation(id=f"SUB-{z.code}-{i + 1}", name=f"{z.short} {side}", zone_id=zid, lat=z.lat + dlat, lng=z.lng + dlng))
        s.add_all(subs)
        s.flush()
        for i, f in enumerate(fs):
            f.substation_id = subs[i * n // len(fs)].id
    s.flush()
    from .services.network import ensure_routes
    ensure_routes(s)  # sandbox feeder routes until the utility's GIS export is imported
    s.commit()


def _ev(s: Session, o: Outage, kind: str, text: str, user: str, at) -> None:
    s.add(OutageEvent(outage_id=o.id, kind=kind, text=text, user_name=user, at=at))


def _historical(s: Session, rng: random.Random, name: str, cat: int, landfall, actual_vs_predicted: float, rain: dict | None = None) -> None:
    """A closed storm with a full, consistent record: tickets, crews' work, ETRs, mutual aid, comms.
    `rain` (rainfall fields) makes it a Rain Event instead of a hurricane."""
    from .services.connector import new_ticket
    from .services.events import RAIN
    e = StormEvent(name=name, kind=RAIN if rain else "Hurricane" if cat else "Tropical Storm", status="closed", category=cat,
                   max_wind_mph=30 if rain else {1: 85, 2: 105}[cat], pressure_mb=1008 if rain else 975 - cat * 5, lat=27.6, lng=-82.7,
                   movement="" if rain else "NE", landfall_at=landfall, track=[], created_at=landfall - timedelta(days=4),
                   activated_at=landfall - timedelta(hours=2), restoring_at=landfall + timedelta(hours=14), closed_at=landfall + timedelta(days=4),
                   **(rain or {}))
    s.add(e)
    s.flush()
    from .services.prediction import predict
    res = predict(s, e, cat)
    s.add(PredictionRun(event_id=e.id, category=cat, result=res, created_at=landfall - timedelta(days=3)))
    zones = {z.id: z for z in s.scalars(select(Zone)).all()}
    feeders: dict = {}
    for f in s.scalars(select(Feeder)).all():
        feeders.setdefault(f.zone_id, []).append(f)
    facilities = {f.feeder_id: f for f in s.scalars(select(Facility)).all()}
    crews = s.scalars(select(Crew).where(Crew.kind == "line")).all()
    weights = {z["id"]: z["pred"] for z in res["zones"]}
    target = res["pred_total"] * actual_vs_predicted
    mean = target / (700 if cat == 2 else 300)
    total = 0
    while total < target:
        zid = rng.choices(list(weights), list(weights.values()))[0]
        rep = landfall + timedelta(hours=rng.uniform(-1, 10))
        o = new_ticket(s, e, zones[zid], feeders[zid], mean, facilities, rng, at=rep)
        crew = rng.choice(crews)
        o.crew_id = crew.id
        o.assigned_at = rep + timedelta(hours=rng.uniform(10, 40))
        hours = ops.job_hours(o)
        o.etr_at = o.assigned_at + timedelta(hours=ops.TRAVEL_H + hours)
        o.started_at = o.assigned_at + timedelta(hours=ops.TRAVEL_H)
        o.restored_at = o.started_at + timedelta(hours=hours * rng.uniform(0.7, 1.45))
        o.status = "restored"
        ops.log(s, o, "assigned", f"Assigned to {crew.code}.", "Luis Ortega")
        ops.log(s, o, "status", "Status in progress → restored", f"{crew.code} (mobile app)")
        total += o.customers
    for company, origin, workers in (("Southern Grid Cooperative", "Georgia", 120 * cat), ("Carolina Power Alliance", "North Carolina", 80 * cat)):
        s.add(MutualAidRequest(event_id=e.id, company=company, origin=origin, kind="line", workers=workers, status="released",
                               requested_at=landfall - timedelta(hours=60), eta=landfall - timedelta(hours=12),
                               arrived_at=landfall - timedelta(hours=14), released_at=landfall + timedelta(days=3), requested_by="Dana Whitaker"))
    for ch, aud, rec in (("sms", "all", 491000), ("x", "all", 48200), ("facebook", "all", 61500), ("email", "all", 373000), ("sms", "out", round(target * 0.71))):
        s.add(Message(event_id=e.id, channel=ch, audience=aud, body=f"{name} update — see bayviewpw.example/outages", status="sent",
                      recipients=rec, created_by="Priya Nair", approved_by="Marcus Reed", ai_generated=True,
                      created_at=landfall - timedelta(hours=30), sent_at=landfall - timedelta(hours=29)))
    for z in zones:
        s.add(PublishedEtr(event_id=e.id, zone_id=z, published_by="Dana Whitaker", published_at=landfall + timedelta(hours=20)))
    for key, title in (("mutual_aid", "Request mutual-aid line workers"), ("precomms", "Draft the pre-storm customer campaign")):
        s.add(Recommendation(event_id=e.id, key=key, priority="High", title=title, detail="", impact="", why="", status="approved",
                             decided_by="Dana Whitaker", decided_at=landfall - timedelta(hours=60), outcome="Done."))
    s.add(AuditLog(at=e.closed_at, user_name="Dana Whitaker", action="event.status", entity="storm_event", entity_id=str(e.id),
                   detail=f"{name}: Restoring → Closed", event_id=e.id))
    s.flush()
