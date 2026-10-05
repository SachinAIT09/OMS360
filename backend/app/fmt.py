"""Formatting helpers. Rounding mirrors JavaScript's Math.round so numbers match the UI."""
import math
from datetime import datetime, timedelta

from .data import LANDFALL


def jround(x: float) -> int:
    return math.floor(x + 0.5)


def fmt(n: float) -> str:
    return f"{jround(n):,}"


def pct(x: float, digits: int = 0) -> str:
    return f"{x * 100:.{digits}f}%"


def add_h(hours: float, base: datetime = LANDFALL) -> datetime:
    """Landfall-relative time, rounded to the nearest 30 minutes."""
    t = base + timedelta(hours=hours)
    secs = jround(t.timestamp() / 1800) * 1800
    return datetime.fromtimestamp(secs, tz=base.tzinfo)


def _clock(d: datetime) -> str:
    h = d.hour % 12 or 12
    return f"{h}:{d.minute:02d} {'AM' if d.hour < 12 else 'PM'}"


def fmt_dt(d: datetime) -> str:
    """e.g. 'Tue, Oct 6, 8:00 PM'"""
    return f"{d:%a}, {d:%b} {d.day}, {_clock(d)}"


def fmt_t(d: datetime) -> str:
    """e.g. 'Tue 8:00 PM'"""
    return f"{d:%a} {_clock(d)}"
