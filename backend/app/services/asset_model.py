"""Asset health model — ILLUSTRATIVE, pending validation by the utility's asset-management engineers.

Every unit gets a health index (HI, 0 end of life … 100 as new) built from explainable penalties, CNAIM-style but simpler.
Penalties (points off 100), each scaled by an adjustable weight (Admin → Asset health model; stored in settings):

  age              age_weight × min(1.5, age / design life)^2.2                         all types
                   design life: power transformer 45 y, pole-mount transformer 35 y, pad-mount 40 y,
                   breaker 40 y, recloser 30 y, wood pole 50 y, steel 80 y, concrete 70 y
  inspection       score 1–5 → 0 / 4 / 10 / 22 / 35                × inspection          all types
  loading          0.6 per % of peak load over nameplate (max 20)    × loading            transformers
  dissolved gas    IEEE C57.104 TDCG condition 1–4 → 0 / 10 / 22 / 35 × oil               power transformers
  oil moisture     > 25 ppm 6, > 35 ppm 12                          × oil
  through-faults   1.5 each (max 15)                                × history
  maintenance      overdue 6; tap changer older than 30 y 4         × maintenance
  pole strength    remaining ground-line strength < 67 % (NESC replacement) 35, < 80 % 15, < 90 % 5   × structure
  switchgear       operations > 80 % of rated 12, > 100 % 25; last test marginal 10, failed 30; oil interrupter
                   older than 35 y 8; test older than 6 y 6         × switchgear          breakers, reclosers

  condition band   Good ≥ 70, Fair ≥ 50, Poor ≥ 30, Critical below (thresholds adjustable)

Missing data is never filled in. No install year → HI is None, condition "Unknown", and the failure probability is a
type-typical estimate (flagged). No inspection, a stale inspection (> 6 y), no oil test or no strength test are listed as
gaps and lower the confidence (high / medium / low). Confirmed storm damage is a separate status set from field reports.

Probability of failure in the next 12 months is Weibull on an effective age: age plus the non-age penalties converted to
years (one age_weight of penalty ≈ one design life). Risk = PoF × customers who lose power when the unit fails (× 2 when a
critical facility is on the circuit).
"""
import json
import math

POWER, DIST, BREAKER, RECLOSER, POLE = "power_transformer", "dist_transformer", "breaker", "recloser", "pole"
KINDS = {POWER: "Substation power transformer", DIST: "Distribution transformer", BREAKER: "Feeder breaker",
         RECLOSER: "Line recloser", POLE: "Distribution pole"}
SWITCHGEAR = (BREAKER, RECLOSER)
POOR = ("Poor", "Critical")
INSPECTION = {1: 0, 2: 4, 3: 10, 4: 22, 5: 35}
WEIBULL = {POWER: (70.0, 3.5), DIST: (60.0, 3.5), BREAKER: (60.0, 3.0), RECLOSER: (45.0, 3.0), POLE: (75.0, 3.2)}
STALE_INSPECTION_Y = 6

DEFAULT_WEIGHTS = {"age_weight": 45.0, "inspection": 1.0, "loading": 1.0, "oil": 1.0, "history": 1.0, "maintenance": 1.0,
                   "structure": 1.0, "switchgear": 1.0, "band_good": 70.0, "band_fair": 50.0, "band_poor": 30.0}
WEIGHT_LABELS = {
    "age_weight": "Age: points off at the end of design life", "inspection": "Inspection score", "loading": "Overloading",
    "oil": "Oil tests (dissolved gas, moisture)", "history": "Through-faults", "maintenance": "Maintenance overdue / tap changer",
    "structure": "Pole remaining strength", "switchgear": "Breaker / recloser wear and tests",
    "band_good": "Good from HI", "band_fair": "Fair from HI", "band_poor": "Poor from HI (below = Critical)"}
WEIGHTS = dict(DEFAULT_WEIGHTS)
SETTING_KEY = "asset_health_weights"


def load_weights(raw: str | None) -> dict:
    """Apply stored weights (JSON) over the defaults; returns the active set."""
    WEIGHTS.clear()
    WEIGHTS.update(DEFAULT_WEIGHTS)
    if raw:
        try:
            WEIGHTS.update({k: float(v) for k, v in json.loads(raw).items() if k in DEFAULT_WEIGHTS})
        except (ValueError, TypeError):
            pass
    return dict(WEIGHTS)


def validate_weights(w: dict) -> dict:
    out = dict(DEFAULT_WEIGHTS)
    for k, v in w.items():
        if k not in DEFAULT_WEIGHTS:
            raise ValueError(f"Unknown weight '{k}'")
        v = float(v)
        if k == "age_weight" and not 5 <= v <= 100 or k.startswith("band_") and not 0 < v < 100 or not k.startswith("band_") and k != "age_weight" and not 0 <= v <= 5:
            raise ValueError(f"{WEIGHT_LABELS[k]}: {v:g} is out of range")
        out[k] = v
    if not out["band_good"] > out["band_fair"] > out["band_poor"]:
        raise ValueError("Bands must satisfy Good > Fair > Poor")
    return out


def life(a) -> float:
    d = a.details or {}
    if a.kind == POWER:
        return 45.0
    if a.kind == DIST:
        return 40.0 if a.mounting == "pad" else 35.0
    if a.kind == BREAKER:
        return 40.0
    if a.kind == RECLOSER:
        return 30.0
    return {"steel": 80.0, "concrete": 70.0}.get(d.get("material"), 50.0)


def _dga_condition(ppm: float | None) -> int:
    if ppm is None:
        return 1
    return 1 if ppm <= 720 else 2 if ppm <= 1920 else 3 if ppm <= 4630 else 4


def band(hi: float | None) -> str:
    if hi is None:
        return "Unknown"
    return "Good" if hi >= WEIGHTS["band_good"] else "Fair" if hi >= WEIGHTS["band_fair"] else "Poor" if hi >= WEIGHTS["band_poor"] else "Critical"


def replacement_cost(a) -> float:
    d = a.details or {}
    if a.kind == POWER:
        return round(a.rating_kva / 1000 * 85000 + (250000 if a.ltc else 0) + 400000, -3)
    if a.kind == BREAKER:
        return 185000.0
    if a.kind == RECLOSER:
        return 48000.0
    if a.kind == POLE:
        return {"steel": 9500.0, "concrete": 8000.0}.get(d.get("material"), 3800.0) + 25.0 * (d.get("height_ft") or 40)
    return float({25: 4200, 37.5: 4800, 50: 5600, 75: 9000, 100: 10500, 167: 15500, 300: 32000, 500: 46000}.get(a.rating_kva, 6000)
                 + (1800 if a.mounting == "pole" else 2500))


def score(a, customers: float, critical: bool, year: int) -> None:
    """Fill the computed fields: health index, condition, drivers, gaps, confidence, 12-month PoF, risk and replacement cost."""
    W = WEIGHTS
    d = a.details or {}
    L = life(a)
    gaps: list[str] = []
    age = None
    if a.install_year is None:
        gaps.append("Install year not recorded — age and health index unknown")
    elif a.install_year > year:
        gaps.append(f"Install year {a.install_year} is in the future — check the record")
    else:
        age = year - a.install_year
    pen: list[tuple[float, str]] = []
    age_pen = W["age_weight"] * min(1.5, age / L) ** 2.2 if age is not None else 0.0
    if age is not None:
        pen.append((age_pen, f"Age {age} y of {L:.0f} y design life"))
    if a.inspection_score:
        pen.append((W["inspection"] * INSPECTION.get(a.inspection_score, 0),
                    f"Inspection score {a.inspection_score}/5" + (f" ({a.last_inspection})" if a.last_inspection else "")))
        if a.last_inspection and year - a.last_inspection > STALE_INSPECTION_Y:
            gaps.append(f"Last inspection {a.last_inspection} — over {STALE_INSPECTION_Y} years old")
    else:
        gaps.append("No inspection on file")
    if a.kind in (POWER, DIST) and a.peak_load_pct and a.peak_load_pct > 100:
        pen.append((W["loading"] * min(20, 0.6 * (a.peak_load_pct - 100)), f"Peak load {a.peak_load_pct:.0f}% of nameplate"))
    if a.kind == POWER:
        if a.dga_tdcg_ppm is None:
            gaps.append("No dissolved-gas (DGA) oil test on file")
        else:
            c = _dga_condition(a.dga_tdcg_ppm)
            pen.append((W["oil"] * {1: 0, 2: 10, 3: 22, 4: 35}[c], f"Dissolved gas {a.dga_tdcg_ppm:,.0f} ppm TDCG (condition {c})"))
        m = a.oil_moisture_ppm or 0
        pen.append((W["oil"] * (12 if m > 35 else 6 if m > 25 else 0), f"Oil moisture {m:.0f} ppm"))
        pen.append((W["history"] * min(15, 1.5 * (a.through_faults or 0)), f"{a.through_faults or 0} through-faults"))
        pen.append((W["maintenance"] * (6 if a.maintenance_overdue else 0), "Maintenance overdue"))
        pen.append((W["maintenance"] * (4 if a.ltc and age is not None and age > 30 else 0), "Tap changer over 30 y"))
    if a.kind == POLE:
        st = d.get("strength_pct")
        if st is None:
            gaps.append("No ground-line strength test on file")
        else:
            pen.append((W["structure"] * (35 if st < 67 else 15 if st < 80 else 5 if st < 90 else 0),
                        f"Remaining strength {st:.0f}% ({d.get('strength_test_year', '—')})" + (" — below NESC replacement level" if st < 67 else "")))
    if a.kind in SWITCHGEAR:
        ops, rated = d.get("operations"), d.get("rated_operations") or 10000
        if ops is not None:
            r = ops / rated
            pen.append((W["switchgear"] * (25 if r > 1 else 12 if r > 0.8 else 0), f"{ops:,} operations of {rated:,} rated"))
        res, ty = d.get("test_result"), d.get("last_test_year")
        if not res:
            gaps.append("No timing / contact-resistance test on file")
        else:
            pen.append((W["switchgear"] * {"pass": 0, "marginal": 10, "fail": 30}.get(res, 0), f"Last test {res} ({ty or '—'})"))
            if ty and year - ty > STALE_INSPECTION_Y:
                pen.append((W["switchgear"] * 6, f"Test overdue (last {ty})"))
        if d.get("interrupter") == "oil" and age is not None and age > 35:
            pen.append((W["switchgear"] * 8, "Oil interrupter over 35 y"))

    other = sum(p for p, _ in pen) - age_pen
    if age is None:
        a.health_index, a.condition = None, "Unknown"
        eff = 0.6 * L + other / W["age_weight"] * L  # type-typical age: an estimate, flagged below
        gaps.append("Failure probability estimated from a typical age for this type")
    else:
        a.health_index = round(max(0.0, min(100.0, 100 - age_pen - other)), 1)
        a.condition = band(a.health_index)
        eff = age + other / W["age_weight"] * L
    a.drivers = [t for p, t in sorted(pen, key=lambda x: -x[0]) if p >= 3][:4]
    a.gaps = gaps
    tests_ok = {POWER: a.dga_tdcg_ppm is not None, POLE: d.get("strength_pct") is not None}.get(a.kind, True) \
        and (a.kind not in SWITCHGEAR or bool(d.get("test_result")))
    recent = bool(a.inspection_score and a.last_inspection and year - a.last_inspection <= 3)
    a.confidence = "low" if age is None or not a.inspection_score else "high" if recent and tests_ok else "medium"
    eta, beta = WEIBULL[a.kind]
    a.pof_12m = round(1 - math.exp(-(((eff + 1) / eta) ** beta - (eff / eta) ** beta)), 5)
    a.risk_score = round(a.pof_12m * customers * (2 if critical else 1), 4)
    a.replacement_cost = replacement_cost(a)


def methodology() -> dict:
    """What the Asset health page shows under 'How the score works'."""
    return {"status": "Illustrative — pending validation by the utility's asset-management engineers",
            "weights": dict(WEIGHTS), "defaults": DEFAULT_WEIGHTS, "labels": WEIGHT_LABELS,
            "design_life": {"Power transformer": 45, "Pole-mount transformer": 35, "Pad-mount transformer": 40, "Breaker": 40,
                            "Recloser": 30, "Wood pole": 50, "Steel pole": 80, "Concrete pole": 70},
            "weibull": {KINDS[k]: {"eta_y": v[0], "beta": v[1]} for k, v in WEIBULL.items()},
            "notes": ["Age alone never makes a unit Poor: inspection, test and loading evidence move the score.",
                      "Missing install years are not filled in: those units show Unknown and an estimated failure probability.",
                      "Confirmed storm damage comes only from field assessments on outage tickets; tornado-path exposure is a prediction.",
                      "Risk = 12-month failure probability × customers affected (× 2 with a critical facility on the circuit)."]}
