"""Customer communications: audiences, recipient counts and AI drafting from live storm data."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..data import MEDICAL_NEEDS
from ..fmt import fmt, fmt_dt, fmt_t, pct
from ..models import Region, StormEvent, Zone
from .events import is_rain

SITE = "bayviewpw.example/outages"
CHANNELS = {"x": "X / Twitter", "facebook": "Facebook", "sms": "SMS", "email": "Email", "ivr": "IVR / phone", "website": "Website banner"}
PURPOSES = {
    "prepare": "Prepare — storm approaching",
    "warning": "Warning — impact within 24 h",
    "outage": "Outage confirmed — crews mobilising",
    "etr": "Restoration times available",
    "restored": "Power restored — verify",
    "medical": "Medical-needs outreach",
    "boil_water": "Precautionary boil-water notice",
}
SOCIAL_FOLLOWERS = {"x": 48200, "facebook": 61500}


def audiences(s: Session, customers_out: int = 0, event: StormEvent | None = None) -> list[dict]:
    zones = s.scalars(select(Zone)).all()
    total = sum(z.customers for z in zones)
    rows = [
        {"id": "all", "name": "All electric customers", "count": total},
        {"id": "water", "name": "Water customers", "count": sum(z.water_customers for z in zones)},
        {"id": "medical", "name": "Medical-needs / life-support", "count": MEDICAL_NEEDS},
        {"id": "coastal", "name": "Coastal surge zones", "count": sum(z.customers for z in zones if z.coastal)},
        {"id": "flood", "name": "Flood-prone zones", "count": sum(z.customers for z in zones if z.coastal or z.vulnerability >= 0.85)},
        {"id": "out", "name": "Customers currently out", "count": customers_out},
    ]
    rows += [{"id": f"zone:{z.id}", "name": f"Zone — {z.short}", "count": z.customers} for z in zones]
    regions = {r.id: r.name for r in s.scalars(select(Region)).all()}
    rows += [{"id": f"region:{rid}", "name": f"Region — {name}", "count": sum(z.customers for z in zones if z.region_id == rid)}
             for rid, name in regions.items()]
    if event is not None and event.status in ("active", "restoring"):
        from .ops import network_etrs
        circuits = network_etrs(s, event)["circuits"]
        rows.append({"id": "circuits_published", "name": "Customers out on circuits with a published ETR",
                     "count": sum(c["customers_out"] for c in circuits if c["published"])})
        rows += [{"id": f"circuit:{c['id']}", "name": f"Circuit {c['id']} — {c['zone']} ({c['substation'] or 'n/a'})", "count": c["customers_out"]}
                 for c in sorted(circuits, key=lambda c: c["id"])]
    return rows


def recipients(channel: str, audience_count: int) -> int:
    if channel in SOCIAL_FOLLOWERS:
        return SOCIAL_FOLLOWERS[channel]
    rate = {"sms": 0.71, "email": 0.54, "ivr": 0.0, "website": 0.0}.get(channel, 0.5)
    return round(audience_count * rate)


def default_purpose(event: StormEvent) -> str:
    return {"monitoring": "prepare", "preparing": "warning", "active": "outage", "restoring": "etr", "closed": "restored"}[event.status]


def _rain_templates(event: StormEvent, ctx: dict, lf: str, lf_t: str, worst: str, tag: str) -> dict:
    """Rain events: rainfall and flooding wording instead of category, wind and landfall."""
    name, out = event.name, ctx.get("customers_out", 0)
    when = f"from ~{lf_t}" if event.landfall_at else "soon"  # rain onset, when known
    rain = f"{event.rain_total_in:g} inches of rain" if event.rain_total_in else "heavy rain"
    return {
        "prepare": {
            "subject": f"Heavy rain ahead: prepare for {name}",
            "short": f"🌧️ {name} could bring {rain} to Tampa Bay {when}. Saturated ground means falling trees and flooding. Our crews are preparing now. Sign up for outage texts → {SITE} {tag}",
            "long": f"{name} is forecast to bring {rain} to Tampa Bay starting {lf}. Flooding and trees falling in saturated soil can cause outages, especially in {worst}.\n\nWhat we're doing: staging crews on high ground, pre-positioning pumps at low-lying substations and protecting water lift stations.\n\nWhat you can do: charge devices, never drive through flooded roads, and text REG to 72990 for outage alerts.",
            "sms": f"Bayview: {name} may bring {rain} and outages {when}. Prepare now. Use medical equipment? Reply MED. Report outages: text OUT. STOP to opt out.",
        },
        "warning": {
            "subject": f"Flood Watch: {name} rain starts within 24 hours",
            "short": f"⚠️ Flood Watch: {name} rain expected {when}. {fmt(ctx.get('line_workers', 0))} line workers are staged on high ground. Stay away from downed lines and flood water. {tag}",
            "long": f"Heavy rain from {name} starts in less than 24 hours.\n\nOur crews are staged on high ground and will restore power as soon as flooded areas are safe to enter.\n\nIf you lose power you don't need to call: smart meters tell us automatically and we'll text your estimated restoration time. Never touch electrical equipment standing in water.",
            "sms": f"Bayview: {name} rain expected {when}. Crews are staged. Smart meters report outages automatically — we'll text your restoration time. Avoid flood water near power lines.",
        },
        "outage": {
            "subject": "We know your power is out",
            "short": f"{name} has caused outages for ~{fmt(out)} customers. Crews are working wherever roads are passable. You don't need to report your outage — our smart meters tell us. {tag}",
            "long": f"Approximately {fmt(out)} customers are without power after {name}. Crews are working wherever flood water allows safe access, starting with hospitals, water plants and medical-needs customers.\n\nWe will publish estimated restoration times by address at {SITE} once damage is assessed.",
            "sms": "Bayview: We know your power is out. Crews work as soon as flooded areas are safe to enter. We'll text your estimated restoration time. Downed line or water near equipment? Call 911.",
        },
    }


def draft(event: StormEvent, channel: str, purpose: str, ctx: dict) -> dict:
    """ctx: pred_total, worst (list of zone names), line_workers, customers_out, restored_pct, zone_etrs [(name, iso dt)]"""
    lf = fmt_dt(event.landfall_at) if event.landfall_at else "in the coming days"
    lf_t = fmt_t(event.landfall_at) if event.landfall_at else "soon"
    worst = ", ".join(ctx.get("worst", [])[:3]) or "coastal areas"
    name, cat = event.name, event.category
    out, rp = ctx.get("customers_out", 0), ctx.get("restored_pct", 0.0)
    etrs = ctx.get("zone_etrs", [])
    tag = "#" + "".join(name.split()[-1:]) + "FL"
    T = {
        "prepare": {
            "subject": f"Prepare for {name} — what to expect from Bayview",
            "short": f"🌀 {name} could reach Tampa Bay as a Cat {cat} {lf_t}. Our crews are preparing now. Charge devices and sign up for outage texts → {SITE} {tag}",
            "long": f"{name} is forecast to approach Tampa Bay {lf} as a Category {cat}. Based on our storm model, extended outages are possible, especially in {worst}.\n\nWhat we're doing: requesting additional crews, staging trucks inland and protecting water lift stations.\n\nWhat you can do: make a plan, charge devices, and text REG to 72990 for outage alerts.",
            "sms": f"Bayview: {name} may cause extended outages from {lf_t}. Prepare now. Use medical equipment? Reply MED. Report outages: text OUT. STOP to opt out.",
        },
        "warning": {
            "subject": f"{name} is less than 24 hours away",
            "short": f"⚠️ Hurricane Warning: {name} (Cat {cat}) expected ~{lf_t}. {fmt(ctx.get('line_workers', 0))} line workers are staged and ready. We restore as soon as winds drop below 39 mph. {tag}",
            "long": f"{name} is less than 24 hours away.\n\nOur crews — including line workers from neighbouring states — are staged at safe inland locations and will begin restoration as soon as it is safe.\n\nIf you lose power you don't need to call: smart meters tell us automatically and we'll text your estimated restoration time.",
            "sms": f"Bayview: {name} landfall expected ~{lf_t}. Crews are staged. If your power goes out, smart meters notify us automatically — we'll text your restoration time.",
        },
        "outage": {
            "subject": "We know your power is out",
            "short": f"{name} has caused outages for ~{fmt(out)} customers. Crews are working as conditions allow. You don't need to report your outage — our smart meters tell us. {tag}",
            "long": f"Approximately {fmt(out)} customers are without power after {name}. Crews begin work as soon as sustained winds are below 39 mph, starting with hospitals, water plants and medical-needs customers.\n\nWe will publish estimated restoration times by address at {SITE} once damage is assessed.",
            "sms": "Bayview: We know your power is out. Crews start as soon as it's safe. We'll text your estimated restoration time after damage assessment. Downed line? Call 911.",
        },
        "etr": {
            "subject": "Your estimated restoration time",
            "short": f"⚡ {pct(rp)} of customers affected by {name} are restored. Look up the estimated restoration time for your address → {SITE} {tag}",
            "long": f"Restoration update: {pct(rp)} of affected customers restored.\n\n" + "\n".join(f"• {n}: {fmt_dt(t)}" for n, t in etrs[:6]) + f"\n\nLook up your address at {SITE}.",
            "sms": "Bayview: An estimated restoration time is now available for your address at " + SITE + ". We'll text you if it changes by more than 1 hour.",
        },
        "restored": {
            "subject": "Power restored — thank you",
            "short": f"✅ {pct(rp)} of customers affected by {name} are restored. Still out while neighbours have power? Text OUT to 72990. {tag}",
            "long": f"{pct(rp)} of customers affected by {name} have their power back. Crews are finishing individual service repairs.\n\nIf you are still without power while neighbours have it, text OUT to 72990 so we can create a ticket.",
            "sms": "Bayview: Power is restored in your area. Still out? Reply OUT and we'll dispatch a crew.",
        },
        "medical": {
            "subject": "Important: plan for your medical equipment",
            "short": "Medical-needs customers: please confirm your storm plan.",
            "long": f"Our records show you rely on powered medical equipment. {name} may cause extended outages. Please confirm your backup plan or arrange to go to a special-needs shelter. Reply or call us to update your details.",
            "sms": f"Bayview: {name} may cause long outages. Your account lists medical equipment — please confirm your backup plan. Reply HELP to talk to us.",
        },
        "boil_water": {
            "subject": "Precautionary boil-water notice",
            "short": f"Precautionary boil-water notice for {worst}. Boil water for 1 minute before drinking until further notice.",
            "long": f"As a precaution after {name}, customers in {worst} should boil tap water for one minute before drinking or cooking until the notice is lifted.",
            "sms": f"Bayview Water: Precautionary boil-water notice for {worst}. Boil water 1 min before use until further notice.",
        },
    }
    if is_rain(event):
        T.update(_rain_templates(event, ctx, lf, lf_t, worst, tag))
    T = T[purpose]
    if channel == "x":
        body = T["short"][:280]
    elif channel == "sms":
        body = T["sms"] + " STOP to opt out." if "STOP" not in T["sms"] else T["sms"]
    elif channel == "ivr":
        body = "Thank you for calling Bayview Power and Water. " + T["long"].split("\n")[0]
    elif channel == "website":
        body = T["short"]
    else:
        body = T["long"]
    return {"subject": T["subject"] if channel == "email" else "", "body": body}
