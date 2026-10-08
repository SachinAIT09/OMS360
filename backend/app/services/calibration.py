"""Confidence calibration: does "85% confidence" really come true 85% of the time?

Confidence on a circuit ETR is meant as the chance the circuit is restored within ±2 hours of the time we told
customers. Each published ETR is kept as an EtrSnapshot; once the circuit is restored we compare. Grouping by
confidence band shows promised vs. actual — the evidence a utility needs before it tells customers a time.

The sandbox has no real publishing history for its past storms, so ensure_history() simulates snapshots for closed
events (flagged simulated=True): ETR errors drawn so each band lands near its promise, slightly overconfident at the
top as real crews' estimates tend to be. Production replaces this with the utility's own history.
"""
import random
from datetime import timedelta
from statistics import NormalDist

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import EtrSnapshot, Outage, StormEvent

WINDOW_H = 2.0
BANDS = [(40, 60), (60, 70), (70, 80), (80, 90), (90, 101)]


def ensure_history(s: Session) -> None:
    """Simulated publishing history for closed events that have none."""
    done = set(s.scalars(select(EtrSnapshot.event_id).distinct()).all())
    for e in s.scalars(select(StormEvent).where(StormEvent.status == "closed")).all():
        if e.id in done:
            continue
        rng = random.Random(7700 + e.id)
        last: dict[str, Outage] = {}
        for o in s.scalars(select(Outage).where(Outage.event_id == e.id, Outage.restored_at.is_not(None))).all():
            if o.feeder_id not in last or o.restored_at > last[o.feeder_id].restored_at:
                last[o.feeder_id] = o
        for fid, o in last.items():
            for hours_before, (clo, chi) in ((18, (52, 68)), (9, (64, 82)), (3, (78, 94))):
                at = o.restored_at - timedelta(hours=hours_before)
                if at < o.reported_at:
                    continue
                conf = rng.randint(clo, chi)
                p = max(0.05, min(0.97, conf / 100 - (0.05 if conf >= 85 else 0)))  # a little overconfident at the top
                sd = WINDOW_H / NormalDist().inv_cdf((1 + p) / 2)
                s.add(EtrSnapshot(event_id=e.id, feeder_id=fid, at=at, confidence=conf, simulated=True,
                                  etr_at=o.restored_at + timedelta(hours=rng.gauss(0.2, sd))))
    s.flush()


def report(s: Session, event_id: int | None = None) -> dict:
    """Promised vs. actual by confidence band, over restored circuits."""
    q = select(EtrSnapshot)
    if event_id:
        q = q.where(EtrSnapshot.event_id == event_id)
    snaps = s.scalars(q).all()
    events = {snap.event_id for snap in snaps}
    restored: dict[tuple[int, str], list[Outage]] = {}
    for o in s.scalars(select(Outage).where(Outage.event_id.in_(events), Outage.restored_at.is_not(None))).all():
        restored.setdefault((o.event_id, o.feeder_id), []).append(o)
    rows = {b: [] for b in BANDS}
    for snap in snaps:
        known = [o for o in restored.get((snap.event_id, snap.feeder_id), []) if o.reported_at <= snap.at]
        open_then = [o for o in known if o.restored_at > snap.at]
        if not open_then:
            continue  # nothing was out on the circuit at that moment
        actual = max(o.restored_at for o in open_then)
        err = abs((actual - snap.etr_at).total_seconds()) / 3600
        band = next(b for b in BANDS if b[0] <= snap.confidence < b[1])
        rows[band].append((snap.confidence, err))
    bands = []
    for (lo, hi), items in rows.items():
        if not items:
            continue
        bands.append({"band": f"{lo}%+" if hi > 100 else f"{lo}–{hi - 1}%", "count": len(items),
                      "promised_pct": round(sum(c for c, _ in items) / len(items), 1),
                      "actual_pct": round(sum(1 for _, x in items if x <= WINDOW_H) / len(items) * 100, 1),
                      "mae_h": round(sum(x for _, x in items) / len(items), 2)})
    n = sum(b["count"] for b in bands)
    return {"window_h": WINDOW_H, "bands": bands, "snapshots": n,
            "simulated_pct": round(sum(1 for snap in snaps if snap.simulated) / len(snaps) * 100) if snaps else 0,
            "gap_pts": round(sum((b["promised_pct"] - b["actual_pct"]) * b["count"] for b in bands) / n, 1) if n else None}
