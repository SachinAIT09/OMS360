"""Recommendations engine.

Rules are evaluated against live state (latest prediction, tickets, crews, mutual aid, messages).
A recommendation is created once per rule per event; approving it executes the action and
records what was created, so every AI decision leaves a trail.
"""
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import bus
from ..data import DA_PARTNER, MA_PARTNERS, MEDICAL_NEEDS, TREE_PARTNER
from ..fmt import fmt
from ..models import (Crew, Message, MutualAidRequest, Outage, PredictionRun, PublishedEtr, Recommendation, StagingYard,
                      StormEvent, Task, utcnow)
from . import comms, ops
from .events import hazard, impact_word, is_rain, scale_label
from .prediction import predict

RECURRING = {"dispatch_backlog", "publish_etrs", "publish_circuit_etrs"}  # can come back after being handled


def latest_prediction(s: Session, event_id: int) -> PredictionRun | None:
    return s.scalars(select(PredictionRun).where(PredictionRun.event_id == event_id).order_by(PredictionRun.id.desc())).first()


def _has_message(s: Session, event_id: int, audience: str | None = None) -> bool:
    q = select(func.count(Message.id)).where(Message.event_id == event_id)
    if audience:
        q = q.where(Message.audience == audience)
    return s.scalar(q) > 0


def _rules(s: Session, e: StormEvent) -> list[dict]:
    """Return the recommendations whose conditions hold right now."""
    out = []
    pr = latest_prediction(s, e.id)
    p = pr.result if pr else None
    prep = e.status in ("monitoring", "preparing")
    now = utcnow()
    hours_to_landfall = (e.landfall_at - now).total_seconds() / 3600 if e.landfall_at else None  # rain events: hours to rain onset
    rain = is_rain(e)
    tornado = hazard(e) == "tornado"
    impact = impact_word(e)

    if prep and not p:
        out.append(dict(key="run_prediction", priority="High", title=f"Run an impact prediction for {e.name}",
                        detail="No outage prediction exists for this event yet. Crew, materials and comms planning depend on it.",
                        impact="Unlocks crew sizing and preparation recommendations",
                        why="Predictions combine the storm's forecast intensity with zone vulnerability, asset exposure and damage from past storms."))
    if prep and p:
        need = p["needed"]
        if need["line"] > 0:
            out.append(dict(key="mutual_aid", priority="Critical",
                            title=f"Request {fmt(need['line'])} mutual-aid line workers + {fmt(need['tree'])} tree workers",
                            detail=f"The {p.get('scenario', scale_label(e, p['category']))} prediction needs {fmt(p['required']['line'])} line workers; {fmt(p['internal']['line'])} are on the roster"
                                   f" and {fmt(p['committed']['line'])} already requested. Crews need 36–60 h to arrive.",
                            impact="Cuts average restoration time by ~" + str(round((1 - min(1, p['coverage']) ** 0.75) * 100)) + "%",
                            why=f"Predicted peak is {fmt(p['pred_total'])} customers out. One line worker restores ~185 customers per storm event in this territory."))
        if s.scalar(select(func.count(StagingYard.id)).where(StagingYard.active.is_(False))):
            out.append(dict(key="staging", priority="High", title="Open all inland staging yards and pre-stage crews",
                            detail="Moves available internal line crews to staging yards outside " + ("flood-prone zones and low-water crossings." if rain else
                                   "the tornado watch box and the forecast storm tracks." if tornado else "surge zones A/B."),
                            impact="Crews on site 6–9 h faster after the all-clear" if not tornado else "Crews roll into damaged areas within an hour of the storms passing",
                            why=("Yards are on high ground, clear of predicted flooding, and within 25 minutes of the highest-impact zones." if rain else
                                 "Crews and trucks parked in a tornado's path are lost with it; yards were picked outside the forecast tracks and within "
                                 "45 minutes of the circuits most likely to be hit." if tornado else
                                 "Yards were selected outside the predicted surge envelope and within 25 minutes of the highest-impact zones.")))
        if rain:
            out.append(dict(key="flood_assets", priority="High", title="Pre-position pumps and high-water vehicles for critical facilities",
                            detail="Portable pumps at substations in low-lying zones, and high-clearance trucks for crews serving hospitals and water plants.",
                            impact="Keeps substations dry and crews able to reach critical customers through standing water",
                            why=f"{p.get('scenario', 'Heavy rain')} on saturated ground floods low-lying substations and roads first."))
        if tornado:
            out.append(dict(key="tornado_logistics", priority="High", title="Line up debris-removal contractors and a transmission patrol",
                            detail=f"{p.get('circuits_in_path', 0)} circuits are on the forecast damage paths. Book debris and tree contractors, a "
                                   "helicopter patrol for transmission lines crossing the paths, and safety crews to make downed lines safe for first responders.",
                            impact="Rebuild starts the morning after instead of waiting for roads to clear",
                            why="In a tornado's core path circuits are rebuilt, not repaired: roads must be cleared and structures assessed first."))
        xr = max(p.get("regions") or [{}], key=lambda r: r.get("xfmrs_in_path", 0) if tornado else r.get("pred", 0))
        if p["materials"].get("transformers") and xr.get("name"):
            out.append(dict(key="xfmr_prestage", priority="High",
                            title=f"Pre-stage {fmt(p['materials']['transformers'])} distribution transformers, most for the {xr['name']} region",
                            detail=(f"{fmt(xr.get('xfmrs_in_path', 0))} transformers sit on {xr.get('circuits_in_path', 0)} {xr['name']} circuits in the "
                                    "forecast damage paths. " if tornado else "")
                                   + "The count comes from each circuit's own transformer register: replacement rates rise 2.5× for units in Poor or "
                                     "Critical condition, so older circuits draw more stock.",
                            impact="No waiting on transformer stock in the first 72 hours",
                            why="Asset age and health say where equipment will fail, not just how many customers will be out."))
        if not _has_message(s, e.id):
            out.append(dict(key="precomms", priority="High", title="Draft the pre-storm customer campaign (X, Facebook, SMS, email, IVR)",
                            detail="Creates AI drafts from the latest prediction and sends them to the approval queue.",
                            impact="Historically −30% inbound calls during the event",
                            why="Customers warned 48–72 h ahead call less and sign up for outage texts, which power automated ETR updates."))
        if not _has_message(s, e.id, "medical"):
            out.append(dict(key="medical", priority="Critical", title=f"Contact {fmt(MEDICAL_NEEDS)} medical-needs customers",
                            detail="Creates SMS and IVR outreach to life-support customers for approval.",
                            impact="Moves vulnerable customers to shelters before " + ("the heaviest rain" if rain else "the storms arrive" if tornado else "landfall"),
                            why="These customers have registered powered medical equipment; most live in zones with high predicted outage probability."))
        if p["generators_needed"]:
            out.append(dict(key="generators", priority="High", title=f"Deploy {p['generators_needed']} portable generators to water lift stations",
                            detail=f"{p['lift_stations_at_risk']} of {p['lift_stations_total']} lift stations lack backup power in predicted outage zones.",
                            impact="Avoids sewer overflows and boil-water notices",
                            why="Lift stations without power overflow within ~6 h."))
        out.append(dict(key="materials", priority="Medium",
                        title=f"Order materials: {fmt(p['materials']['poles'])} poles, {fmt(p['materials']['transformers'])} transformers",
                        detail="Inventory covers ~35% of predicted need; vendors need 48 h lead time.",
                        impact="Prevents a materials bottleneck on day 2–3",
                        why="Usage per 1,000 customers out is taken from the last three major storms."))
        if hours_to_landfall is not None and hours_to_landfall < (12 if tornado else 36) and not rain:
            out.append(dict(key="eoc", priority="High", title="Activate the Emergency Operations Center — Level 1",
                            detail="Opens a 24/7 storm desk, logistics cell and County EOC liaison.", impact=f"One command structure through {impact}",
                            why="The Storm Prediction Center has a High Risk / tornado watch over the territory." if tornado else
                                "Forecast sustained winds exceed the Level-1 activation threshold (74 mph)."))
        if e.status == "preparing" and hours_to_landfall is not None and hours_to_landfall < 6:
            out.append(dict(key="activate", priority="Critical", title=f"Move {e.name} to Active",
                            detail=("Heavy rain is about to start." if rain else "Storms are about to fire." if tornado else "Landfall is imminent.")
                                   + " Activating starts outage intake from the OMS/AMI connector into this event.",
                            impact="Outage tickets are tracked against this storm",
                            why="Heavy rain is expected within 6 hours." if rain else "Tornadoes are expected within 6 hours." if tornado else
                                "Hurricane conditions are expected within 6 hours."))

    if e.status in ("active", "restoring"):
        st = ops.event_stats(s, e)
        idle = st["crews_by_status"].get("available", 0) + st["crews_by_status"].get("staged", 0)
        if st["unassigned"] and idle:
            out.append(dict(key="dispatch_backlog", priority="Critical" if st["critical_open"] else "High",
                            title=f"Auto-dispatch {min(st['unassigned'], idle)} idle crews to the unassigned backlog",
                            detail=f"{st['unassigned']} tickets are unassigned; {idle} crews are idle. Critical facilities first, then by customers affected.",
                            impact="Starts restoration on the highest-impact outages now",
                            why="Greedy nearest-crew dispatch ordered by priority and customer count minimises customer-hours out."))
        unpublished = [z for z in st["zones"] if z["open_tickets"] and not z["published"]]
        if unpublished:
            out.append(dict(key="publish_etrs", priority="High", title=f"Publish restoration times for {len(unpublished)} zones",
                            detail="Customers see a specific time on the outage map and receive SMS instead of 'multiple days'.",
                            impact="Fewer calls; customers can plan", why="ETRs are computed from open tickets, assigned crews and damage type."))
        ready = [c for c in ops.network_etrs(s, e)["circuits"] if not c["published"] and c["confidence"] >= ops.PUBLISH_CONFIDENCE]
        if ready:
            out.append(dict(key="publish_circuit_etrs", priority="High",
                            title=f"Publish circuit-level ETRs for {len(ready)} circuits at ≥{ops.PUBLISH_CONFIDENCE}% confidence",
                            detail=f"{fmt(sum(c['customers_out'] for c in ready))} customers on these circuits get a specific restoration time for their own circuit "
                                   "instead of the zone-wide one.",
                            impact="Tighter, more trustworthy ETRs for smaller areas",
                            why="These circuits have damage assessed and crews committed, so their ETRs are unlikely to move."))
        if not _has_message(s, e.id, "out") and st["customers_out"]:
            out.append(dict(key="outage_notice", priority="High", title=f"Notify {fmt(st['customers_out'])} customers that their outage is known",
                            detail="SMS to affected meters plus a website banner.", impact="Prevents call-center overload",
                            why="AMI meters have reported last-gasp signals for these customers."))
        arrived = s.scalars(select(MutualAidRequest).where(MutualAidRequest.event_id == e.id, MutualAidRequest.status == "arrived")).all()
        if e.status == "restoring" and arrived and st["customers_affected"] and st["customers_out"] < 0.1 * st["customers_affected"]:
            out.append(dict(key="release_mutual_aid", priority="Medium", title=f"Release {len(arrived) // 2 or 1} mutual-aid contingents",
                            detail="Less than 10% of affected customers remain out; in-house crews can finish.",
                            impact="Saves ~$4,200 per worker per day", why="Released crews finish in-progress work first."))
        if e.status == "restoring" and st["restored_pct"] > 0.8:
            out.append(dict(key="verify", priority="High", title='Send "Still out? Reply OUT" verification to restored customers',
                            detail="Finds nested single-service outages the OMS cannot see.", impact="Typically surfaces 1–2% hidden outages",
                            why="Feeder restoration does not guarantee every service drop is energised."))
        if e.status == "restoring" and st["open_tickets"] == 0:
            out.append(dict(key="close", priority="Medium", title=f"Close {e.name}",
                            detail="All tickets are restored. Closing freezes the event for reporting.", impact="Event moves to reports and the after-action review",
                            why="No open tickets remain."))
    return out


def refresh(s: Session, e: StormEvent) -> list[Recommendation]:
    if e.status == "closed":
        return list(s.scalars(select(Recommendation).where(Recommendation.event_id == e.id).order_by(Recommendation.id.desc())))
    current = {r["key"]: r for r in _rules(s, e)}
    existing = s.scalars(select(Recommendation).where(Recommendation.event_id == e.id).order_by(Recommendation.id)).all()
    latest = {}
    for r in existing:
        latest[r.key] = r
    now = utcnow()
    for key, rule in current.items():
        r = latest.get(key)
        if r and r.status == "open":
            for f in ("priority", "title", "detail", "impact", "why"):
                setattr(r, f, rule[f])
        elif not r or (key in RECURRING and r.decided_at and now - r.decided_at > timedelta(minutes=5)):
            s.add(Recommendation(event_id=e.id, **rule))
    for key, r in latest.items():
        if r.status == "open" and key not in current:
            s.delete(r)  # condition no longer holds
    s.commit()
    return list(s.scalars(select(Recommendation).where(Recommendation.event_id == e.id).order_by(Recommendation.id.desc())))


def _drafts(s: Session, e: StormEvent, purpose: str, channels: list[str], audience: str, user: str) -> int:
    from .context import comms_context
    ctx = comms_context(s, e)
    aud = {a["id"]: a for a in comms.audiences(s, ctx.get("customers_out", 0))}[audience]
    for ch in channels:
        d = comms.draft(e, ch, purpose, ctx)
        s.add(Message(event_id=e.id, channel=ch, audience=audience, subject=d["subject"], body=d["body"], status="pending",
                      ai_generated=True, recipients=comms.recipients(ch, aud["count"]), created_by=f"AI Assistant for {user}"))
    bus.publish("messages")
    return len(channels)


def execute(s: Session, e: StormEvent, r: Recommendation, user: str) -> str:
    k = r.key
    if k == "run_prediction":
        res = predict(s, e)
        s.add(PredictionRun(event_id=e.id, category=res["category"], result=res))
        return f"Prediction run: {fmt(res['pred_total'])} customers predicted out."
    if k == "mutual_aid":
        p = latest_prediction(s, e.id).result
        need = p["needed"]
        n = 0
        for company, origin, share in MA_PARTNERS:
            workers = round(need["line"] * share)
            if workers:
                s.add(MutualAidRequest(event_id=e.id, company=company, origin=origin, kind="line", workers=workers,
                                       eta=utcnow() + timedelta(hours=40), requested_by=user)); n += 1
        if need["tree"]:
            s.add(MutualAidRequest(event_id=e.id, company=TREE_PARTNER[0], origin=TREE_PARTNER[1], kind="tree",
                                   workers=need["tree"], eta=utcnow() + timedelta(hours=36), requested_by=user)); n += 1
        if need["da"]:
            s.add(MutualAidRequest(event_id=e.id, company=DA_PARTNER[0], origin=DA_PARTNER[1], kind="assessment",
                                   workers=need["da"], eta=utcnow() + timedelta(hours=24), requested_by=user)); n += 1
        bus.publish("mutual_aid")
        return f"{n} mutual-aid requests sent to partner utilities."
    if k == "staging":
        yards = s.scalars(select(StagingYard)).all()
        crews = s.scalars(select(Crew).where(Crew.source == "internal", Crew.status == "available")).all()
        for y in yards:
            y.active = True
        for i, c in enumerate(crews[: len(crews) // 2]):
            y = yards[i % len(yards)]
            c.status, c.yard_id, c.lat, c.lng = "staged", y.id, y.lat + (i % 9) * 0.003, y.lng + (i // 9 % 9) * 0.003
        bus.publish("crews")
        return f"{len(yards)} yards opened; {len(crews) // 2} crews staged."
    if k == "precomms":
        n = _drafts(s, e, comms.default_purpose(e), ["x", "facebook", "sms", "email", "ivr"], "all", user)
        return f"{n} AI drafts sent to the approval queue."
    if k == "medical":
        n = _drafts(s, e, "medical", ["sms", "ivr"], "medical", user)
        return f"{n} medical-needs messages sent to the approval queue."
    if k == "outage_notice":
        n = _drafts(s, e, "outage", ["sms", "website"], "out", user)
        return f"{n} outage notices sent to the approval queue."
    if k == "verify":
        n = _drafts(s, e, "restored", ["sms"], "all", user)
        return "Verification SMS sent to the approval queue."
    if k in ("generators", "materials", "eoc", "flood_assets", "tornado_logistics", "xfmr_prestage"):
        title = r.title
        s.add(Task(event_id=e.id, title=title, owner_role="ops_manager", due_at=e.landfall_at or utcnow() + timedelta(hours=24)))
        bus.publish("tasks")
        return "Task created and assigned to Operations."
    if k == "activate":
        from .events import change_status
        change_status(s, e, "active", user)
        return "Event is now Active."
    if k == "close":
        from .events import change_status
        change_status(s, e, "closed", user)
        return "Event closed."
    if k == "dispatch_backlog":
        n = ops.auto_dispatch(s, e, user)
        bus.publish("outages")
        return f"{n} tickets dispatched."
    if k == "publish_etrs":
        st = ops.event_stats(s, e)
        n = 0
        for z in st["zones"]:
            if z["open_tickets"] and not z["published"]:
                s.add(PublishedEtr(event_id=e.id, zone_id=z["id"], published_by=user)); n += 1
        bus.publish("restoration")
        return f"ETRs published for {n} zones."
    if k == "publish_circuit_etrs":
        from ..routers.field import publish_circuits
        n = publish_circuits(s, e, user)
        bus.publish("restoration")
        return f"ETRs published for {n} circuits."
    if k == "release_mutual_aid":
        arrived = s.scalars(select(MutualAidRequest).where(MutualAidRequest.event_id == e.id, MutualAidRequest.status == "arrived")).all()
        n = sum(ops.release_mutual_aid(s, req) for req in arrived[: len(arrived) // 2 or 1])
        bus.publish("crews")
        return f"{n} mutual-aid crews released."
    return "Done."
