"""Jarvis — deterministic intent engine over live operational data.

Replies are structured so the UI renders them safely:
  text (supports **bold**), bullets, quote, actions [{label, kind: approve|nav, value}], say (TTS)
"""
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..data import SURGE_BY_CAT
from ..fmt import fmt, fmt_dt, fmt_t, pct
from ..models import Message, MutualAidRequest, Recommendation, StormEvent, Zone
from . import comms, ops
from .context import comms_context
from .events import is_rain
from .prediction import predict
from .recommendations import latest_prediction


def _reply(text, bullets=None, actions=None, say="", quote=None):
    return {"text": text, "bullets": bullets or [], "actions": actions or [], "say": say or re.sub(r"\*\*", "", text), "quote": quote}


def _nav(label, path):
    return {"label": label, "kind": "nav", "value": path}


def greeting(user_name: str, event: StormEvent | None) -> dict:
    first = user_name.split()[0]
    if not event:
        return _reply(f"Hi {first}. No storm event is open right now. Ask me about past events, crews or the network.")
    return _reply(f"Hi {first}. I'm tracking **{event.name}** ({event.status}). Ask me what we need to do, whether we have enough "
                  f"crews, or when any neighbourhood will be restored.")


def answer(s: Session, q_raw: str, e: StormEvent | None, weather: dict | None = None) -> dict:
    q = q_raw.lower().strip()
    if not e:
        return _reply("There's no active storm event selected. Open **Storm Events** to create one or import from the National Hurricane Center.",
                      actions=[_nav("Storm Events", "/events")])
    pr = latest_prediction(s, e.id)
    p = pr.result if pr else None
    st = ops.event_stats(s, e)
    live = e.status in ("active", "restoring")
    zones = {z.short.lower(): z for z in s.scalars(select(Zone)).all()}
    zone = next((z for k, z in zones.items() if k in q), None)
    cat_m = re.search(r"cat(?:egory)?\s*([1-5])", q)
    rain_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:in|inch|inches|\")\b", q)
    rain = is_rain(e)
    ev = f"/events/{e.id}"
    after = "after the rain starts" if rain else "after landfall"

    if rain and rain_m and re.search(r"what if|if it|becomes|scenario|more|worse|instead", q):
        r_in = float(rain_m.group(1))
        p2 = predict(s, e, rain_in=r_in)
        base = p["pred_total"] if p else 0
        return _reply(f"If {e.name} brings **{r_in:g} inches of rain**:",
                      [f"Predicted outages: **{fmt(p2['pred_total'])}**" + (f" ({'+' if p2['pred_total'] >= base else ''}{fmt(p2['pred_total'] - base)} vs current prediction)" if p else ""),
                       f"Line workers needed: **{fmt(p2['required']['line'])}** — still to request: {fmt(p2['needed']['line'])}",
                       f"95% restored about **{p2['p95_eta_h']} h** after the rain starts", f"Lift stations at risk: {p2['lift_stations_at_risk']}"],
                      [_nav("Open prediction", f"{ev}?tab=prediction")],
                      f"With {r_in:g} inches of rain, about {fmt(p2['pred_total'])} customers would lose power.")

    if cat_m and not rain and re.search(r"what if|if it|becomes|scenario|stronger|worse|instead", q):
        c = int(cat_m.group(1))
        p2 = predict(s, e, c)
        base = p["pred_total"] if p else 0
        return _reply(f"If {e.name} makes landfall as a **Category {c}**:",
                      [f"Predicted outages: **{fmt(p2['pred_total'])}**" + (f" ({'+' if p2['pred_total'] >= base else ''}{fmt(p2['pred_total'] - base)} vs current prediction)" if p else ""),
                       f"Line workers needed: **{fmt(p2['required']['line'])}** — still to request: {fmt(p2['needed']['line'])}",
                       f"95% restored about **{p2['p95_eta_h']} h** after landfall", f"Storm surge: {SURGE_BY_CAT[c]}"],
                      [_nav("Open prediction", f"{ev}?tab=prediction")],
                      f"At category {c}, about {fmt(p2['pred_total'])} customers would lose power.")

    if re.search(r"(more|enough|how many).*(people|crew|worker|line|staff|resource)|mutual aid|staff|do i need", q) and "water" not in q:
        ma = s.scalars(select(MutualAidRequest).where(MutualAidRequest.event_id == e.id, MutualAidRequest.status != "cancelled")).all()
        ma_line = [f"{r.company} — {r.workers} {r.kind} workers, {r.status.replace('_', ' ')}" for r in ma]
        if not p:
            return _reply("I need an impact prediction before I can size crews.", actions=[_nav("Run prediction", f"{ev}?tab=prediction")])
        if p["needed"]["line"] > 0:
            rec = s.scalars(select(Recommendation).where(Recommendation.event_id == e.id, Recommendation.key == "mutual_aid", Recommendation.status == "open")).first()
            acts = [{"label": "Request mutual aid", "kind": "approve", "value": rec.id}] if rec else []
            return _reply(f"**Yes — you need more people.** The {p.get('scenario', 'Cat ' + str(p['category']))} prediction needs **{fmt(p['required']['line'])}** line workers. "
                          f"You have {fmt(p['internal']['line'])} on the roster and {fmt(p['committed']['line'])} requested — a gap of **{fmt(p['needed']['line'])}**.",
                          ma_line or ["No mutual aid requested yet. Crews need 36–60 h to arrive."], acts + [_nav("Open crews", "/crews")],
                          f"Yes. You still need {fmt(p['needed']['line'])} more line workers.")
        return _reply(f"**You're covered.** {fmt(p['internal']['line'] + p['committed']['line'])} line workers rostered or requested against {fmt(p['required']['line'])} needed.",
                      ma_line, [_nav("Open crews", "/crews")], "You're covered for line workers.")

    if re.search(r"unassigned|backlog|dispatch|tickets", q):
        idle = st["crews_by_status"].get("available", 0) + st["crews_by_status"].get("staged", 0)
        rec = s.scalars(select(Recommendation).where(Recommendation.event_id == e.id, Recommendation.key == "dispatch_backlog", Recommendation.status == "open")).first()
        return _reply(f"**{st['open_tickets']}** open tickets, **{st['unassigned']}** unassigned ({st['critical_open']} critical). {idle} crews are idle.",
                      actions=([{"label": "Auto-dispatch now", "kind": "approve", "value": rec.id}] if rec else []) + [_nav("Open outages", "/outages")],
                      say=f"{st['unassigned']} tickets are unassigned and {idle} crews are idle.")

    if re.search(r"hospital|critical|facilit|shelter|medical", q):
        if live:
            from ..models import Outage, Facility
            crit = s.scalars(select(Outage).where(Outage.event_id == e.id, Outage.priority == "critical", Outage.status.in_(ops.OPEN))).all()
            facs = {f.id: f.name for f in s.scalars(select(Facility)).all()}
            return _reply(f"**{len(crit)} critical-facility outages** are open.",
                          [f"{o.number} — {facs.get(o.facility_id, o.feeder_id)}: {o.status.replace('_', ' ')}" + (f", crew {o.crew.code}" if o.crew else "") for o in crit[:6]],
                          [_nav("Open outages", "/outages?priority=critical")], f"{len(crit)} critical facility outages are open.")
        if p:
            risky = [f for f in p["facilities"] if f["risk"] != "Low"]
            return _reply(f"**{len(risky)} critical facilities** are in medium or high-risk zones.",
                          [f"{f['name']} — {f['risk']} risk, feeder {f['feeder']}, backup {f['backup']}" for f in risky],
                          [_nav("Open prediction", f"{ev}?tab=prediction")], f"{len(risky)} critical facilities are at risk.")

    if re.search(r"water|lift|boil|sewer", q) and p:
        return _reply(f"**{p['lift_stations_at_risk']}** of {p['lift_stations_total']} lift stations are in predicted outage areas without backup power; "
                      f"I recommend **{p['generators_needed']} portable generators**." +
                      (f" Coastal zones ({', '.join(p['boil_water_zones'])}) may need precautionary boil-water notices." if p["boil_water_zones"] else ""),
                      actions=[_nav("Open prediction", f"{ev}?tab=prediction")])

    if re.search(r"post|tweet|draft|social|facebook|announce|message", q) and not re.search(r"pending|approv", q):
        ctx = comms_context(s, e)
        d = comms.draft(e, "x", comms.default_purpose(e), ctx)
        txt = d["body"]
        if zone and live:
            zr = next(z for z in st["zones"] if z["id"] == zone.id)
            txt = (f"Update for {zone.short}: {fmt(zr['customers_out'])} customers out, crews assigned. Estimated restoration: "
                   f"{fmt_dt(zr['etr_at'])}. Details → bayviewpw.example/outages" if zr["etr_at"] else f"Update for {zone.short}: power is restored.")
        return _reply("Here's a draft for X. Open Communications to send it for approval:", quote=txt, actions=[_nav("Open communications", "/communications")],
                      say="I've drafted a post. You can send it for approval in communications.")

    if re.search(r"pending|approv", q):
        n = s.scalar(select(func.count(Message.id)).where(Message.event_id == e.id, Message.status == "pending"))
        r = s.scalar(select(func.count(Recommendation.id)).where(Recommendation.event_id == e.id, Recommendation.status == "open"))
        return _reply(f"**{n}** messages are waiting for approval and **{r}** recommendations need a decision.",
                      actions=[_nav("Approval queue", "/communications?tab=pending"), _nav("Overview", "/")])

    fdr_m = re.search(r"fdr-[a-z]{3}-\d{2}", q)
    region_m = re.search(r"(north|central|east|south(?: shore)?)\s+region|region\s+(north|central|east|south)", q)
    if not live and p and p.get("circuits") and (fdr_m or region_m):
        if fdr_m:
            c = next((c for c in p["circuits"] if c["id"] == fdr_m.group(0).upper()), None)
            if c:
                return _reply(f"Circuit **{c['id']}** ({c['substation']}, {c['zone']}): predicted {fmt(c['pred'])} of {fmt(c['customers'])} customers out; "
                              f"restoration about **{c['eta_h']:.0f} h {after}** (likely {c['low_h']:.0f}–{c['high_h']:.0f} h, {c['confidence']}% confidence).",
                              actions=[_nav("Open prediction", f"{ev}?tab=prediction")],
                              say=f"Circuit {c['id']} should be restored about {c['eta_h']:.0f} hours {after}.")
        else:
            key = (region_m.group(1) or region_m.group(2)).split()[0]
            r = next((r for r in p.get("regions", []) if r["name"].lower().startswith(key)), None)
            if r:
                return _reply(f"**{r['name']} region** (predicted): {fmt(r['pred'])} customers out on {r['circuits']} circuits. Typical customer back about "
                              f"**{r['eta_h']:.0f} h {after}** ({r['low_h']:.0f}–{r['high_h']:.0f} h); last circuit about {r['last_h']:.0f} h (up to {r['last_high_h']:.0f} h).",
                              actions=[_nav("Open prediction", f"{ev}?tab=prediction")])

    if live and (fdr_m or region_m):
        net = ops.network_etrs(s, e)
        if fdr_m:
            fid = fdr_m.group(0).upper()
            c = next((c for c in net["circuits"] if c["id"] == fid), None)
            if not c:
                return _reply(f"Circuit **{fid}** has no open outages.", say=f"Circuit {fid} has no open outages.")
            return _reply(f"Circuit **{fid}** ({c['substation'] or 'substation n/a'}, {c['zone']}): {fmt(c['customers_out'])} customers out on "
                          f"{c['open_tickets']} tickets, {c['crews']} crews. Estimated restoration: **{fmt_dt(c['etr_at'])}** ({c['confidence']}% confidence)"
                          + (" — published to customers." if c["published"] else "."),
                          actions=[_nav("Restoration board", "/restoration?level=circuit")],
                          say=f"Circuit {fid} should be restored by {fmt_dt(c['etr_at'])}, {c['confidence']} percent confidence.")
        key = (region_m.group(1) or region_m.group(2)).split()[0]
        r = next((r for r in net["regions"] if r["name"].lower().startswith(key)), None)
        if r:
            cs = sorted((c for c in net["circuits"] if c["region_id"] == r["id"]), key=lambda c: -c["customers_out"])[:5]
            if not cs:
                return _reply(f"The **{r['name']}** region has no open outages.")
            return _reply(f"**{r['name']} region** ({', '.join(r['zones'])}): {fmt(r['customers_out'])} customers out on {r['circuits_out']} circuits. "
                          f"Last circuit expected **{fmt_dt(r['etr_at'])}** ({r['confidence']}% confidence); {r['circuits_ready']} circuits ready to publish.",
                          [f"{c['id']} ({c['zone']}): {fmt(c['customers_out'])} out, ETR {fmt_t(c['etr_at'])}, {c['confidence']}%" for c in cs],
                          [_nav("Restoration board", "/restoration?level=circuit")])

    if re.search(r"when|restor|etr|back on|power back|how long", q):
        if live:
            if zone:
                zr = next(z for z in st["zones"] if z["id"] == zone.id)
                if not zr["etr_at"]:
                    return _reply(f"**{zone.short}** has no open outages.", say=f"{zone.short} has no open outages.")
                return _reply(f"**{zone.short}**: {fmt(zr['customers_out'])} customers out on {zr['open_tickets']} tickets, {zr['crews']} crews working. "
                              f"Estimated restoration: **{fmt_dt(zr['etr_at'])}** ({zr['confidence']}% confidence)" + (" — published to customers." if zr["published"] else "."),
                              actions=[_nav("Restoration board", "/restoration")], say=f"{zone.short} should be restored by {fmt_dt(zr['etr_at'])}.")
            return _reply(f"**{pct(st['restored_pct'])}** of affected customers are restored; {fmt(st['customers_out'])} still out." +
                          (f" Last zone expected **{fmt_dt(st['last_etr_at'])}**." if st["last_etr_at"] else ""),
                          [f"{z['short']}: {fmt_t(z['etr_at'])}" for z in sorted(st["zones"], key=lambda z: z["etr_at"] or e.created_at, reverse=True) if z["etr_at"]][:5],
                          [_nav("Restoration board", "/restoration")])
        if p:
            zr = next((z for z in p["zones"] if zone and z["id"] == zone.id), None)
            if zr:
                return _reply(f"**{zone.short}**: predicted {fmt(zr['pred'])} customers out ({pct(zr['pct'])}); restoration expected about **{zr['eta_h']} h {after}**"
                              + (f" (~{fmt_dt(_after(e, zr['eta_h']))})." if e.landfall_at else "."),
                              say=f"{zone.short} would be restored about {zr['eta_h']} hours {after}.")
            return _reply(f"Predicted average restoration: **{p['avg_eta_h']:.0f} h** {after}; 95% by **{p['p95_eta_h']} h**.",
                          actions=[_nav("Open prediction", f"{ev}?tab=prediction")])

    if re.search(r"worst|hardest|most affected|which (area|zone|neighbo)", q):
        if live:
            top = sorted(st["zones"], key=lambda z: -z["customers_out"])[:3]
            return _reply("Hardest hit right now:", [f"**{z['short']}** — {fmt(z['customers_out'])} customers out ({pct(z['pct_out'])})" for z in top],
                          [_nav("Outage map", "/outages?view=map")], f"The hardest hit areas are {', '.join(z['short'] for z in top)}.")
        if p:
            top = sorted(p["zones"], key=lambda z: -z["pred"])[:3]
            return _reply("Hardest hit (predicted):", [f"**{z['short']}** — {fmt(z['pred'])} customers ({pct(z['pct'])}), {z['driver'].lower()}" for z in top],
                          [_nav("Open prediction", f"{ev}?tab=prediction")], f"The hardest hit areas are predicted to be {', '.join(z['short'] for z in top)}.")

    if re.search(r"cost|budget|spend|money", q):
        ma = s.scalars(select(MutualAidRequest).where(MutualAidRequest.event_id == e.id, MutualAidRequest.status != "cancelled")).all()
        days = max(3, (p["avg_eta_h"] if p else 48) / 24)
        crews_cost = sum(r.workers * r.cost_per_worker_day for r in ma) * days
        mats = (p["pred_total"] if p else st["customers_affected"]) * 38
        return _reply(f"Estimated storm cost: **${(crews_cost + mats) / 1e6:.1f}M**.",
                      [f"Mutual aid: ${crews_cost / 1e6:.1f}M ({sum(r.workers for r in ma):,} workers × ~{days:.0f} days)", f"Materials & logistics: ${mats / 1e6:.1f}M"],
                      say=f"The estimated storm cost is {(crews_cost + mats) / 1e6:.1f} million dollars.")

    if re.search(r"weather|wind|landfall|where.*storm|rain|surge|track", q):
        w = ""
        if weather and not weather.get("error"):
            w = f" Live conditions in Tampa ({weather['source']}): {round(weather['temp_f'])}°F, wind {round(weather['wind_mph'])} mph, gusts {round(weather['gust_mph'])} mph."
        if rain:
            onset = f" Rain starts {fmt_dt(e.landfall_at)}." if e.landfall_at else ""
            return _reply(f"**{e.name}** — {e.kind}, {e.rain_total_in or 0:g} in forecast at up to {e.rain_rate_in_hr or 0:g} in/hr over ~{e.duration_h or 0:g} h, "
                          f"soil {round((e.soil_saturation or 0) * 100)}% saturated.{onset}{w}", actions=[_nav("Open event", ev)])
        lf = f" Landfall {fmt_dt(e.landfall_at)}." if e.landfall_at else ""
        return _reply(f"**{e.name}** — {e.kind}, Cat {e.category}, {e.max_wind_mph} mph, {e.pressure_mb} mb, moving {e.movement or 'n/a'}.{lf}{w}",
                      actions=[_nav("Open event", ev)])

    if re.search(r"how many|customers out|outage|affected", q):
        if live:
            return _reply(f"**{fmt(st['customers_out'])}** customers are out on {st['open_tickets']} open tickets. {fmt(st['customers_affected'])} affected in total, {pct(st['restored_pct'])} restored.",
                          say=f"{fmt(st['customers_out'])} customers are currently out.")
        if p:
            return _reply(f"No storm outages yet. The prediction is **{fmt(p['pred_total'])}** customers ({pct(p['pred_total'] / p['total_customers'])}) at peak.")

    if re.search(r"what (should|do) (we|i)|priorit|brief|status|summar|first|next|update me|situation", q):
        recs = s.scalars(select(Recommendation).where(Recommendation.event_id == e.id, Recommendation.status == "open")
                         .order_by(Recommendation.priority)).all()
        order = {"Critical": 0, "High": 1, "Medium": 2}
        recs = sorted(recs, key=lambda r: order.get(r.priority, 3))
        state = (f"{fmt(st['customers_out'])} customers out, {pct(st['restored_pct'])} restored, {st['unassigned']} tickets unassigned." if live else
                 (f"Predicted peak {fmt(p['pred_total'])} customers." if p else "No prediction yet."))
        text = f"**{e.name} — {e.status.title()}.** {state}"
        if not recs:
            return _reply(text + " No open recommendations. ✓")
        return _reply(text + " Top priorities:", [r.title for r in recs[:3]],
                      [{"label": "Approve: " + r.title[:38] + "…", "kind": "approve", "value": r.id} for r in recs[:2]],
                      f"Your top priority is: {recs[0].title}.")

    return _reply("I can help with crews, backlog, restoration times, hardest-hit areas, critical facilities, water, cost, scenarios and messages. Try:",
                  ['"Give me a situation briefing"', '"Do I need more people?"', '"When will Riverview be restored?"', '"What if it becomes a Cat 4?"'],
                  say="Here are some things you can ask me.")


def _after(e: StormEvent, hours: float):
    from datetime import timedelta
    return e.landfall_at + timedelta(hours=hours)
