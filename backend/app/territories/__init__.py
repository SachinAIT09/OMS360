"""Territory profiles: the geography, brand and demo scenario a deployment runs with.

Pick one with the OMS360_TERRITORY environment variable (default: oklahoma). Each territory keeps its own database
file, so switching never mixes one territory's network and events into another's.
  oklahoma — Prairie Sky Power, statewide Oklahoma; tornadoes
  tampa    — Bayview Power & Water, Hillsborough County FL; hurricanes
"""
import importlib
import os

AVAILABLE = ("oklahoma", "tampa")
NAME = (os.environ.get("OMS360_TERRITORY") or "oklahoma").strip().lower()
if NAME not in AVAILABLE:
    raise RuntimeError(f"OMS360_TERRITORY must be one of {', '.join(AVAILABLE)} (got '{NAME}')")

active = importlib.import_module(f".{NAME}", __name__)
for _z in active.ZONES:
    _z.setdefault("coastal", False)
    _z.setdefault("crit", False)
    _z.setdefault("med", False)
