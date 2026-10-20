"""Asset history, confirmed damage, recommendations and work orders.

Three things are kept apart on purpose:
  known condition   the register and its inspection / test history (AssetEvent rows)
  predicted         a storm prediction's exposure for the unit's circuit (in a tornado path, share predicted out)
  confirmed damage  set only when a field crew assesses an outage ticket whose damaged device is this unit
                    (Outage.asset_id); restoring the ticket records the repair or replacement.
"""
import random
import zlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Asset, AssetEvent, Facility, Feeder, Outage, PredictionRun, Region, StormEvent, Substation, WorkOrder, Zone, utcnow
from .asset_model import BREAKER, DIST, KINDS, POLE, POOR, POWER, RECLOSER, STALE_INSPECTION_Y, SWITCHGEAR, methodology

DAMAGE_KIND = {"transformer": DIST, "pole": POLE}  # ticket damage type → the asset type it names
FIELD_STATUSES = ("assessed", "assigned", "in_progress", "restored")


def _jan(year: int, month: int = 6) -> datetime:
    return datetime(year, month, 15, tzinfo=timezone.utc)


# ---------------------------------------------------------------- sandbox history
def seed_history(s: Session) -> int:
    """Inspection / test / maintenance history consistent with each unit's current record (sandbox only)."""
    if s.scalar(select(AssetEvent.id).where(AssetEvent.source == "Sandbox history").limit(1)):
        return 0
    year = utcnow().year
    rows = []
    q = select(Asset).where(Asset.source == "sandbox", (Asset.kind != DIST) | Asset.condition.in_(POOR))
    units = s.scalars(q).all()
    for a in units:
        rng = random.Random(zlib.crc32(("h" + a.id).encode()))
        d = a.details or {}
        if a.kind == POWER:
            for back in range(4, -1, -1):
                y = year - back
                if a.install_year and y < a.install_year:
                    continue
                dga = round(a.dga_tdcg_ppm * 0.82 ** back) if a.dga_tdcg_ppm else None
                sc = max(1, (a.inspection_score or 2) - (1 if back >= 3 else 0))
                rows.append({"asset_id": a.id, "at": _jan(y, 4), "kind": "inspection", "source": "Sandbox history",
                             "summary": f"Annual inspection: score {sc}/5" + (f"; DGA {dga:,} ppm TDCG" if dga else "; oil sample not taken"),
                             "data": {"score": sc, **({"dga_tdcg_ppm": dga} if dga else {})}})
            for y in range(year - (6 if a.maintenance_overdue else 3), year - 12, -4):
                if not a.install_year or y >= a.install_year:
                    rows.append({"asset_id": a.id, "at": _jan(y, 9), "kind": "maintenance", "source": "Sandbox history",
                                 "summary": "Oil filtration and bushing clean" + ("; tap changer service" if a.ltc else ""), "data": {}})
        elif a.kind in SWITCHGEAR:
            ty, res = d.get("last_test_year"), d.get("test_result")
            if ty and res:
                rows.append({"asset_id": a.id, "at": _jan(ty, 5), "kind": "test", "source": "Sandbox history",
                             "summary": f"Timing and contact-resistance test: {res}", "data": {"result": res, "operations": d.get("operations")}})
                if ty - 4 >= (a.install_year or 0):
                    rows.append({"asset_id": a.id, "at": _jan(ty - 4, 5), "kind": "test", "source": "Sandbox history",
                                 "summary": "Timing and contact-resistance test: pass", "data": {"result": "pass"}})
        elif a.kind == POLE and d.get("strength_pct") is not None:
            rows.append({"asset_id": a.id, "at": _jan(d.get("strength_test_year") or year, 3), "kind": "test", "source": "Sandbox history",
                         "summary": f"Ground-line inspection: {d['strength_pct']:.0f}% remaining strength", "data": {"strength_pct": d["strength_pct"]}})
        elif a.kind == DIST and a.last_inspection:
            rows.append({"asset_id": a.id, "at": _jan(a.last_inspection, 7), "kind": "inspection", "source": "Sandbox history",
                         "summary": f"Visual inspection: score {a.inspection_score}/5" + (" — corrosion, oil seep" if (a.inspection_score or 0) >= 4 else ""),
                         "data": {"score": a.inspection_score}})
        if rng.random() < 0.0:  # placeholder for future failure history from sources other than outage tickets
            pass
    for u in units:  # read-only here: keep thousands of units out of the session so later autoflushes stay cheap
        s.expunge(u)
    for i in range(0, len(rows), 5000):
        s.execute(AssetEvent.__table__.insert(), rows[i:i + 5000])
    s.commit()
    return len(rows)


# ---------------------------------------------------------------- outage ticket ↔ asset
def pick_asset(s: Session, feeder_id: str, damage: str, number: str) -> Asset | None:
    """The unit a ticket's damage names: a transformer or pole on the ticket's circuit (stable per ticket number)."""
    kind = DAMAGE_KIND.get(damage)
    if not kind:
        return None
    cache = s.info.setdefault("asset_ids", {})  # per session: storm seeding opens thousands of tickets
    key = (feeder_id, kind)
    if key not in cache:
        with s.no_autoflush:
            cache[key] = s.scalars(select(Asset.id).where(Asset.feeder_id == feeder_id, Asset.kind == kind).order_by(Asset.id)).all()
    ids = cache[key]
    if not ids:
        return None
    return s.get(Asset, ids[zlib.crc32(number.encode()) % len(ids)])


def sync_ticket(s: Session, o: Outage, rescore_now: bool = True, have: set | None = None) -> str | None:
    """Confirmed damage follows the field: once a crew has assessed the ticket the named unit is 'damaged'; when the ticket is
    restored the unit is recorded as replaced (transformers, poles) and back in service. Idempotent."""
    if not o.asset_id or o.status not in FIELD_STATUSES or o.damage not in DAMAGE_KIND:
        return None
    a = s.get(Asset, o.asset_id)
    if not a:
        return None
    if have is None:
        have = {k for (k,) in s.execute(select(AssetEvent.kind).where(AssetEvent.outage_id == o.id)).all()}
    e = s.get(StormEvent, o.event_id) if o.event_id else None
    when = o.reported_at or utcnow()
    if "damage" not in have:
        s.add(AssetEvent(asset_id=a.id, at=when, kind="damage", outage_id=o.id, event_id=o.event_id, source="Field assessment",
                         summary=f"Damage confirmed on ticket {o.number}" + (f" ({e.name})" if e else "") + f": {o.damage}, cause {o.cause}",
                         data={"cause": o.cause, "damage": o.damage}))
        if o.status != "restored":
            a.status = "damaged"
    if o.status == "restored" and "replacement" not in have:
        at = o.restored_at or utcnow()
        s.add(AssetEvent(asset_id=a.id, at=at, kind="replacement", outage_id=o.id, event_id=o.event_id, source="Field crew",
                         summary=f"Replaced under ticket {o.number}" + (f" ({e.name})" if e else ""), data={"previous_install_year": a.install_year}))
        a.install_year, a.inspection_score, a.last_inspection, a.status = at.year, 1, at.year, "in_service"
        if a.kind == POLE:
            a.details = {**(a.details or {}), "strength_pct": 100.0, "strength_test_year": at.year}
        if rescore_now:
            from .assets import rescore
            rescore(s, [a.id])
        return a.id
    return None


def backfill(s: Session) -> int:
    """Apply sync_ticket to every ticket that names a unit (seeded history, and tickets moved outside set_status); replaced
    units are re-scored in one batch."""
    replaced: list[str] = []
    done = {oid for (oid,) in s.execute(select(AssetEvent.outage_id).where(AssetEvent.kind == "replacement", AssetEvent.outage_id.is_not(None))).all()}
    damaged = {oid for (oid,) in s.execute(select(AssetEvent.outage_id).where(AssetEvent.kind == "damage", AssetEvent.outage_id.is_not(None))).all()}
    touched = []
    tickets = s.scalars(select(Outage).where(Outage.asset_id.is_not(None), Outage.status.in_(FIELD_STATUSES))).all()
    with s.no_autoflush:
        for o in tickets:
            if o.id in done or (o.id in damaged and o.status != "restored"):
                continue
            aid = sync_ticket(s, o, rescore_now=False, have={"damage"} if o.id in damaged else set())
            touched.append(o.id)
            if aid:
                replaced.append(aid)
    if replaced:
        from .assets import rescore
        rescore(s, replaced)
    s.commit()
    return len(touched)


# ---------------------------------------------------------------- exposure, recommendations
def _latest_runs(s: Session) -> list[tuple[StormEvent, PredictionRun]]:
    out = []
    for e in s.scalars(select(StormEvent).where(StormEvent.status != "closed").order_by(StormEvent.created_at.desc())).all():
        pr = s.scalars(select(PredictionRun).where(PredictionRun.event_id == e.id).order_by(PredictionRun.id.desc())).first()
        if pr:
            out.append((e, pr))
    return out


def exposure(s: Session, a: Asset) -> list[dict]:
    """Predicted storm exposure of the unit's circuit (or, for substation units, its worst circuit) in each open event."""
    fids = [a.feeder_id] if a.feeder_id else list(s.scalars(select(Feeder.id).where(Feeder.substation_id == a.substation_id)).all())
    out = []
    for e, pr in _latest_runs(s):
        cs = [c for c in pr.result.get("circuits") or [] if c["id"] in fids]
        if not cs:
            continue
        c = max(cs, key=lambda c: (c.get("core", 0), c["pct"]))
        out.append({"event_id": e.id, "event": e.name, "kind": e.kind, "status": e.status, "circuit": c["id"], "in_path": bool(c.get("in_path")),
                    "core": c.get("core"), "path_km": c.get("path_km"), "path_ef": c.get("path_ef"), "pct": c["pct"], "eta_h": c["eta_h"],
                    "basis": "Prediction — not confirmed damage"})
    return out


def recommendations(a: Asset, exp: list[dict], year: int) -> list[dict]:
    d = a.details or {}
    out = []

    def rec(key, kind, priority, title, reason):
        out.append({"key": key, "kind": kind, "priority": priority, "title": title, "reason": reason})

    if a.status == "damaged":
        rec("damaged", "replace", "Critical", "Repair or replace the storm-damaged unit", "Damage confirmed by a field assessment.")
    in_path = next((x for x in exp if x["in_path"]), None)
    if in_path and a.status != "damaged":
        rec("storm_inspect", "inspect", "High" if a.condition in POOR or a.condition == "Unknown" else "Medium",
            f"Inspect after {in_path['event']} passes",
            f"Circuit {in_path['circuit']} is in the predicted EF{in_path['path_ef']} damage path ({in_path['basis'].lower()}).")
    if a.condition == "Critical":
        rec("replace", "replace", "High", "Plan replacement", f"Health index {a.health_index:.0f} (Critical): {', '.join((a.drivers or [])[:2])}.")
    elif a.condition == "Poor":
        rec("refurbish", "maintain", "Medium", "Schedule refurbishment or replacement review", f"Health index {a.health_index:.0f} (Poor).")
    if a.install_year is None:
        rec("records", "inspect", "Medium", "Confirm the install year", "Age is not recorded, so health cannot be scored.")
    if not a.inspection_score or (a.last_inspection and year - a.last_inspection > STALE_INSPECTION_Y):
        rec("inspect", "inspect", "Medium", "Inspect: no recent inspection", f"Last inspection: {a.last_inspection or 'none on file'}.")
    if a.kind == POWER and a.dga_tdcg_ppm and a.dga_tdcg_ppm > 1920:
        rec("dga", "test", "High", "Repeat the oil (DGA) test within 30 days", f"TDCG {a.dga_tdcg_ppm:,.0f} ppm (IEEE C57.104 condition ≥ 3).")
    if a.kind == POWER and a.maintenance_overdue:
        rec("maint", "maintain", "Medium", "Complete overdue maintenance", "Maintenance is past its scheduled date.")
    if a.kind == POLE and d.get("strength_pct") is not None:
        if d["strength_pct"] < 67:
            rec("pole_replace", "replace", "High", "Replace the pole", f"Remaining strength {d['strength_pct']:.0f}% is below the NESC replacement level (67%).")
        elif d["strength_pct"] < 80:
            rec("pole_restore", "repair", "Medium", "Reinforce the pole (truss / restoration)", f"Remaining strength {d['strength_pct']:.0f}%.")
    if a.kind in SWITCHGEAR:
        if d.get("test_result") == "fail":
            rec("sw_fail", "replace", "High", "Overhaul or replace — failed last test", f"Test {d.get('last_test_year')}: fail.")
        ops, rated = d.get("operations"), d.get("rated_operations") or 10000
        if ops and ops > 0.8 * rated:
            rec("sw_ops", "maintain", "Medium", "Interrupter maintenance (operations count)", f"{ops:,} of {rated:,} rated operations.")
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    return sorted(out, key=lambda r: order[r["priority"]])


def wo_serial(w: WorkOrder) -> dict:
    return {"id": w.id, "asset_id": w.asset_id, "kind": w.kind, "title": w.title, "reason": w.reason, "priority": w.priority, "status": w.status,
            "due_at": w.due_at, "event_id": w.event_id, "created_by": w.created_by, "created_at": w.created_at, "updated_at": w.updated_at}


def asset_detail(s: Session, asset_id: str) -> dict | None:
    from .assets import serial
    from .ops import network_index
    a = s.get(Asset, asset_id)
    if not a:
        return None
    year = utcnow().year
    idx = network_index(s)
    sub = s.get(Substation, a.substation_id) if a.substation_id else None
    zone = s.get(Zone, a.zone_id)
    region = s.get(Region, zone.region_id) if zone and zone.region_id else None
    info = idx.get(a.feeder_id, {}) if a.feeder_id else {}
    events = s.scalars(select(AssetEvent).where(AssetEvent.asset_id == a.id).order_by(AssetEvent.at.desc())).all()
    history = [{"id": ev.id, "at": ev.at, "kind": ev.kind, "summary": ev.summary, "data": ev.data or {}, "source": ev.source,
                "event_id": ev.event_id, "outage_id": ev.outage_id} for ev in events]
    if a.last_inspection and not any(h["kind"] in ("inspection", "test") and h["at"].year == a.last_inspection for h in history):
        history.append({"id": None, "at": _jan(a.last_inspection, 7), "kind": "inspection", "source": "Register (latest only)",
                        "summary": f"Latest inspection on the register: score {a.inspection_score}/5" if a.inspection_score else "Latest inspection on the register",
                        "data": {}, "event_id": None, "outage_id": None})
        history.sort(key=lambda h: h["at"], reverse=True)
    exp = exposure(s, a)
    outages = s.scalars(select(Outage).where((Outage.asset_id == a.id) | ((Outage.feeder_id == a.feeder_id) & Outage.status.in_(
        ("reported", "assessed", "assigned", "in_progress")))).order_by(Outage.reported_at.desc()).limit(12)).all() if a.feeder_id else \
        s.scalars(select(Outage).where(Outage.asset_id == a.id).limit(12)).all()
    ev_names = {e.id: e.name for e in s.scalars(select(StormEvent)).all()}
    crit = s.scalars(select(Facility).where(Facility.feeder_id == a.feeder_id)).all() if a.feeder_id else []
    wos = s.scalars(select(WorkOrder).where(WorkOrder.asset_id == a.id).order_by(WorkOrder.id.desc())).all()
    return {**serial(a, year),
            "parents": {"region_id": region.id if region else None, "region": region.name if region else None, "zone_id": a.zone_id,
                        "zone": zone.short if zone else None, "substation_id": a.substation_id, "substation": sub.name if sub else None,
                        "circuit_id": a.feeder_id, "circuit_customers": info.get("customers")},
            "critical_facilities": [f.name for f in crit],
            "history": [h | {"event": ev_names.get(h["event_id"])} for h in history],
            "exposure": exp, "recommendations": recommendations(a, exp, year),
            "work_orders": [wo_serial(w) for w in wos],
            "outages": [{"id": o.id, "number": o.number, "event": ev_names.get(o.event_id), "status": o.status, "damage": o.damage, "cause": o.cause,
                         "customers": o.customers, "reported_at": o.reported_at, "restored_at": o.restored_at, "this_unit": o.asset_id == a.id}
                        for o in outages],
            "model_status": methodology()["status"]}


def create_work_order(s: Session, a: Asset, kind: str, title: str, reason: str, priority: str, user: str, due_days: int | None,
                      event_id: int | None) -> WorkOrder:
    w = WorkOrder(asset_id=a.id, kind=kind, title=title[:160], reason=reason, priority=priority, status="open", created_by=user,
                  event_id=event_id, due_at=utcnow() + timedelta(days=due_days) if due_days else None)
    s.add(w)
    s.flush()
    return w


def work_orders(s: Session, status: str | None = None, region: str | None = None, limit: int = 200) -> list[dict]:
    q = select(WorkOrder, Asset).join(Asset, Asset.id == WorkOrder.asset_id)
    if status:
        q = q.where(WorkOrder.status.in_(status.split(",")))
    if region:
        q = q.where(Asset.zone_id.in_(select(Zone.id).where(Zone.region_id == region)))
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    rows = [wo_serial(w) | {"asset_name": a.name, "asset_kind": a.kind, "feeder_id": a.feeder_id, "substation_id": a.substation_id}
            for w, a in s.execute(q.order_by(WorkOrder.id.desc()).limit(limit)).all()]
    return sorted(rows, key=lambda r: (r["status"] in ("done", "cancelled"), order.get(r["priority"], 4)))


# ---------------------------------------------------------------- statewide storm impact
def storm_impact(s: Session, e: StormEvent) -> dict:
    """What a storm means for the network, in one place: regions, substations and circuits on the predicted paths (or most
    affected), assets on those circuits that need inspection, confirmed damage so far, and critical facilities."""
    from .ops import event_stats, network_index
    pr = s.scalars(select(PredictionRun).where(PredictionRun.event_id == e.id).order_by(PredictionRun.id.desc())).first()
    p = pr.result if pr else None
    idx = network_index(s)
    circuits = (p or {}).get("circuits") or []
    tornado = (p or {}).get("kind") == "tornado"
    hit = [c for c in circuits if c.get("in_path")] if tornado else [c for c in circuits if c["pct"] >= 0.3]
    hit_ids = {c["id"] for c in hit}
    subs = sorted({idx[c]["substation_id"] for c in hit_ids if c in idx and idx[c]["substation_id"]})
    sub_names = {x.id: x.name for x in s.scalars(select(Substation).where(Substation.id.in_(subs))).all()} if subs else {}
    inspect = dict(s.execute(select(Asset.kind, func.count(Asset.id)).where(Asset.feeder_id.in_(hit_ids)).group_by(Asset.kind)).all()) if hit_ids else {}
    inspect_poor = dict(s.execute(select(Asset.kind, func.count(Asset.id)).where(Asset.feeder_id.in_(hit_ids), Asset.condition.in_(POOR + ("Unknown",)))
                                  .group_by(Asset.kind)).all()) if hit_ids else {}
    confirmed = s.execute(select(Asset.kind, func.count(func.distinct(AssetEvent.asset_id))).join(Asset, Asset.id == AssetEvent.asset_id)
                          .where(AssetEvent.event_id == e.id, AssetEvent.kind == "damage").group_by(Asset.kind)).all()
    facilities = s.scalars(select(Facility).where(Facility.feeder_id.in_(hit_ids))).all() if hit_ids else []
    regions = {}
    for c in circuits:
        r = regions.setdefault(c.get("region_id"), {"id": c.get("region_id"), "name": c.get("region") or "Unassigned", "pred": 0, "circuits_hit": 0,
                                                   "customers_on_hit": 0})
        r["pred"] += c["pred"]
        if c["id"] in hit_ids:
            r["circuits_hit"] += 1
            r["customers_on_hit"] += c["customers"]
    st = event_stats(s, e)
    return {"event_id": e.id, "basis": "prediction" if p else None, "kind": (p or {}).get("kind"), "scenario": (p or {}).get("scenario"),
            "simulation": True, "pred_total": (p or {}).get("pred_total"),
            "regions_affected": sorted([r for r in regions.values() if r["pred"] > 0], key=lambda r: -r["pred"]),
            "circuits_hit": [{k: c.get(k) for k in ("id", "zone", "substation", "region", "customers", "pred", "pct", "eta_h", "path_ef", "core")} for c in hit],
            "substations_exposed": [{"id": x, "name": sub_names.get(x, x)} for x in subs],
            "assets_on_hit_circuits": [{"kind": k, "label": KINDS[k], "units": inspect.get(k, 0), "poor_or_unknown": inspect_poor.get(k, 0)}
                                       for k in (DIST, POLE, RECLOSER, BREAKER) if inspect.get(k)],
            "confirmed_damage": [{"kind": k, "label": KINDS.get(k, k), "units": n} for k, n in confirmed],
            "critical_facilities": [{"name": f.name, "type": f.type, "feeder": f.feeder_id} for f in facilities],
            "live": {"customers_out": st["customers_out"], "open_tickets": st["open_tickets"], "restored_pct": st["restored_pct"],
                     "customers_affected": st["customers_affected"]}}
