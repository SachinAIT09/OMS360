from app.db import SessionLocal
from app.models import Asset
from app.services import assets

from .conftest import login


def _a(**kw):
    base = dict(id="X", kind=assets.DIST, name="t", zone_id="okc", lat=0, lng=0, install_year=2000, rating_kva=50, mounting="pole",
                inspection_score=2, peak_load_pct=80)
    return Asset(**(base | kw))


def test_health_falls_with_age_and_condition():
    young, old, older = _a(install_year=2020), _a(install_year=1990), _a(install_year=1970)
    for a in (young, old, older):
        assets.score(a, 10, False, year=2026)
    assert young.health_index > old.health_index > older.health_index
    assert young.pof_12m < old.pof_12m < older.pof_12m
    assert young.condition == "Good" and older.condition in ("Poor", "Critical")
    assert older.drivers and older.drivers[0].startswith("Age")
    gas = [_a(kind=assets.POWER, mounting="sub", rating_kva=28000, install_year=1990, dga_tdcg_ppm=ppm, ltc=True) for ppm in (300, 2500, 6000)]
    for a in gas:
        assets.score(a, 20000, True, year=2026)
    assert gas[0].health_index > gas[1].health_index > gas[2].health_index
    assert gas[2].risk_score > gas[0].risk_score and "Dissolved gas" in " ".join(gas[2].drivers)


def test_rollups_are_consistent(client, ops_h):
    sm = client.get("/api/assets/summary", headers=ops_h).json()
    with SessionLocal() as s:
        n_dist = s.query(Asset).filter(Asset.kind == assets.DIST).count()
    assert sm["distribution"]["xfmrs"] == n_dist == sum(r["xfmrs"] for r in sm["regions"])
    assert sum(sm["bands"].values()) == n_dist == sum(h["count"] for h in sm["age_histogram"])
    assert 0.03 < sm["distribution"]["pct_poor"] < 0.4  # a plausible, aging but not failed, fleet
    central = next(r for r in sm["regions"] if r["name"] == "Central")
    circuits = client.get("/api/assets/circuits", headers=ops_h, params={"region": central["id"]}).json()
    assert circuits and all(c["region_id"] == central["id"] for c in circuits)
    assert sum(c["xfmrs"] for c in circuits) == central["xfmrs"]
    d = client.get(f"/api/assets/circuits/{circuits[0]['id']}", headers=ops_h, params={"limit": 5}).json()
    assert len(d["transformers"]) == min(5, d["xfmrs"]) and sum(h["count"] for h in d["age_histogram"]) == d["xfmrs"]
    assert d["power_transformers"] and all(a["kind"] == assets.POWER for a in d["power_transformers"])
    subs = client.get("/api/assets/substations", headers=ops_h).json()
    assert subs == sorted(subs, key=lambda a: -a["risk_score"])


def test_asset_health_raises_circuit_storm_risk(client, ops_h, outbreak):
    """Make one fringe circuit's transformers old and failing: its predicted share out and restoration time go up."""
    before = client.post(f"/api/events/{outbreak['id']}/predictions", headers=ops_h, json={"save": False}).json()["result"]["circuits"]
    c = next(c for c in sorted(before, key=lambda c: -c["pred"]) if not c["in_path"] and c["pred"] > 20)
    with SessionLocal() as s:
        for a in s.query(Asset).filter(Asset.feeder_id == c["id"]):
            a.install_year, a.inspection_score = 1962, 5
        assets.rescore(s)
        s.commit()
    after = {x["id"]: x for x in client.post(f"/api/events/{outbreak['id']}/predictions", headers=ops_h, json={"save": False}).json()["result"]["circuits"]}
    assert after[c["id"]]["asset_hi"] < c["asset_hi"]
    assert after[c["id"]]["pred"] > c["pred"] and after[c["id"]]["eta_h"] > c["eta_h"]


def test_import_asset_register(client, ops_h):
    admin = login(client, "admin")
    sample = client.get("/api/admin/assets/sample", headers=admin).json()
    r = client.post("/api/admin/assets/import", headers=admin, json={"csv": sample["csv"]}).json()
    assert r["added"] == 5 and r["updated"] == 0 and r["missing_install_year"] == 1  # every equipment type, one without an install year
    r = client.post("/api/admin/assets/import", headers=admin, json={"csv": sample["csv"]}).json()
    assert r["added"] == 0 and r["updated"] == 5
    unit = client.get("/api/assets/item/PT-NEW-1", headers=ops_h).json()
    assert unit["kind"] == assets.POWER and unit["install_year"] == 1969 and unit["health_index"] < 60 and unit["source"] == "imported"
    blank = client.get("/api/assets/item/DT-NEW-0002", headers=ops_h).json()
    assert blank["install_year"] is None and blank["age"] is None and blank["health_index"] is None and blank["condition"] == "Unknown"
    assert blank["confidence"] == "low" and any("Install year not recorded" in g for g in blank["gaps"]) and any("No inspection" in g for g in blank["gaps"])
    pole = client.get("/api/assets/item/PL-NEW-0001", headers=ops_h).json()
    assert pole["details"]["strength_pct"] == 63 and any("NESC" in d for d in pole["drivers"])
    assert any(r["key"] == "pole_replace" for r in pole["recommendations"])
    future = "id,kind,feeder_id,install_year\nDT-X,dist_transformer,{f},2999".format(f=pole["feeder_id"])
    bad = client.post("/api/admin/assets/import", headers=admin, json={"csv": future})
    assert bad.status_code == 422 and "install_year" in bad.json()["detail"]
    bad = client.post("/api/admin/assets/import", headers=admin, json={"csv": "id,kind,feeder_id,install_year\nDT-1,dist_transformer,NOPE,1990"})
    assert bad.status_code == 422 and "Row 2" in bad.json()["detail"]
    assert client.post("/api/admin/assets/import", headers=login(client, "priya.nair"), json={"csv": sample["csv"]}).status_code == 403
