"""Shared read-models used by comms drafting and Jarvis."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Crew, StormEvent
from . import ops


def comms_context(s: Session, e: StormEvent) -> dict:
    from .recommendations import latest_prediction
    pr = latest_prediction(s, e.id)
    p = pr.result if pr else None
    st = ops.event_stats(s, e)
    worst = [z["short"] for z in sorted(p["zones"], key=lambda z: -z["pred"])[:3]] if p else \
        [z["short"] for z in sorted(st["zones"], key=lambda z: -z["customers_out"])[:3]]
    line_workers = s.scalar(select(func.sum(Crew.size)).where(Crew.kind == "line", Crew.status != "released")) or 0
    return {
        "pred_total": p["pred_total"] if p else 0, "worst": worst, "line_workers": line_workers,
        "customers_out": st["customers_out"], "restored_pct": st["restored_pct"],
        "zone_etrs": [(z["short"], z["etr_at"]) for z in sorted(st["zones"], key=lambda z: z["etr_at"] or e.created_at) if z["etr_at"]],
    }
