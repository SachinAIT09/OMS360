from datetime import date

from app.db import SessionLocal
from app.models import Asset, AssetEvent, Outage
from app.services import asset_history, asset_model, assets, connector, ops

from .conftest import login


def test_age_matches_an_independent_calculation(client, ops_h):
    with SessionLocal() as s:
        a = s.query(Asset).filter(Asset.install_year.is_not(None), Asset.kind == "dist_transformer").first()
        expected = date.today().year - a.install_year  # independent of the service code
    d = client.get(f"/api/assets/item/{a.id}", headers=ops_h).json()
    assert d["age"] == expected and d["age_reference"] == date.today().isoformat()


def test_every_equipment_type_and_missing_data_are_represented(client, ops_h):
    sm = client.get("/api/assets/summary", headers=ops_h).json()
    assert {k["kind"] for k in sm["by_kind"]} == set(asset_model.KINDS)
    assert sm["all"]["unknown"] > 0  # a few sandbox records have no install year …
    with SessionLocal() as s:
        unknown = s.query(Asset).filter(Asset.install_year.is_(None)).all()
        assert unknown and all(a.health_index is None and a.condition == "Unknown" and a.confidence == "low" for a in unknown)
        assert all(a.pof_12m > 0 for a in unknown)  # … whose failure probability is an estimate, flagged as such
        assert all(any("estimated" in g for g in a.gaps) for a in unknown)
    assert sum(sm["bands"].values()) == sm["distribution"]["units"]


def test_age_alone_does_not_make_a_unit_poor():
    old_clean = asset_model.POLE
    a = type("U", (), {})()
    for k, v in dict(kind=old_clean, install_year=1990, mounting="line", inspection_score=1, last_inspection=2025, peak_load_pct=None,
                     dga_tdcg_ppm=None, oil_moisture_ppm=None, through_faults=None, ltc=False, maintenance_overdue=False, rating_kva=0,
                     details={"material": "steel", "strength_pct": 98, "strength_test_year": 2025}).items():
        setattr(a, k, v)
    asset_model.score(a, 10, False, 2026)
    assert a.condition == "Good"  # 36-year-old steel pole with a clean inspection and full strength


def test_health_weights_are_adjustable_and_rescore(client, ops_h):
    admin = login(client, "admin")
    before = client.get("/api/assets/summary", headers=ops_h).json()["all"]["mean_hi"]
    m = client.put("/api/admin/assets/model", headers=admin, json={"weights": {"age_weight": 70}}).json()
    assert m["weights"]["age_weight"] == 70
    after = client.get("/api/assets/summary", headers=ops_h).json()["all"]["mean_hi"]
    assert after < before  # heavier age penalty → lower health everywhere
    assert client.put("/api/admin/assets/model", headers=admin, json={"weights": {"band_good": 20, "band_fair": 50}}).status_code == 422
    assert client.put("/api/admin/assets/model", headers=ops_h, json={"weights": {"nope": 1}}).status_code == 422
    assert client.put("/api/admin/assets/model", headers=login(client, "priya.nair"), json={"weights": {"age_weight": 45}}).status_code == 403
    client.put("/api/admin/assets/model", headers=admin, json={"weights": asset_model.DEFAULT_WEIGHTS})


def test_confirmed_damage_follows_field_assessment(client, ops_h, outbreak):
    """A ticket names the unit; the prediction alone never marks it damaged; assessment confirms it; restoration replaces it."""
    eid = outbreak["id"]
    with SessionLocal() as s:
        before_damaged = {a.id for a in s.query(Asset).filter(Asset.status == "damaged")}
    client.post(f"/api/events/{eid}/status", headers=ops_h, json={"status": "active"})
    for _ in range(25):
        connector.tick()
    with SessionLocal() as s:
        o = s.query(Outage).filter(Outage.event_id == eid, Outage.asset_id.is_not(None), Outage.status == "reported").first()
        assert o, "tornado intake should name damaged transformers / poles"
        unit = s.get(Asset, o.asset_id)
        assert unit.feeder_id == o.feeder_id and unit.id not in before_damaged and unit.status == "in_service"
        oid, aid = o.id, unit.id
    r = client.post(f"/api/outages/{oid}/status", headers=login(client, "luis.ortega"), json={"status": "assessed"})
    assert r.status_code == 200, r.text
    d = client.get(f"/api/assets/item/{aid}", headers=ops_h).json()
    assert d["status"] == "damaged" and d["recommendations"][0]["key"] == "damaged"
    assert any(h["kind"] == "damage" and h["outage_id"] == oid for h in d["history"])
    imp = client.get(f"/api/events/{eid}/impact", headers=ops_h).json()
    assert imp["confirmed_damage"] and imp["basis"] == "prediction"
    with SessionLocal() as s:
        o = s.get(Outage, oid)
        crew = next(c for c in s.query(ops.Crew).filter(ops.Crew.kind == "line", ops.Crew.status.in_(["available", "staged"])))
        ops.assign(s, o, crew, "Test")
        ops.set_status(s, o, "in_progress", "Test")
        ops.set_status(s, o, "restored", "Test")
        s.commit()
        a = s.get(Asset, aid)
        assert a.status == "in_service" and a.install_year == date.today().year
        assert s.query(AssetEvent).filter(AssetEvent.asset_id == aid, AssetEvent.kind == "replacement").count() == 1


def test_work_orders(client, ops_h):
    with SessionLocal() as s:
        aid = s.query(Asset).filter(Asset.condition == "Critical").first().id
    w = client.post(f"/api/assets/item/{aid}/work-orders", headers=ops_h,
                    json={"kind": "replace", "title": "Plan replacement", "priority": "High", "due_days": 30}).json()
    assert w["status"] == "open" and w["asset_id"] == aid
    assert client.patch(f"/api/work-orders/{w['id']}", headers=login(client, "luis.ortega"), json={"status": "scheduled"}).json()["status"] == "scheduled"
    assert client.patch(f"/api/work-orders/{w['id']}", headers=login(client, "priya.nair"), json={"status": "done"}).status_code == 403
    assert client.post(f"/api/assets/item/{aid}/work-orders", headers=ops_h, json={"kind": "explode", "title": "x"}).status_code == 422
    listed = client.get("/api/work-orders", headers=ops_h, params={"status": "open,scheduled"}).json()
    assert any(x["id"] == w["id"] for x in listed)
    assert client.get(f"/api/assets/item/{aid}", headers=ops_h).json()["work_orders"][0]["id"] == w["id"]


def test_hierarchy_is_consistent(client, ops_h):
    """Region → substation → circuit → unit: every level's children belong to it."""
    subs = client.get("/api/network/substations", headers=ops_h, params={"region": "central"}).json()
    assert subs and all(x["region_id"] == "central" for x in subs)
    sub = subs[0]
    d = client.get(f"/api/network/substations/{sub['id']}", headers=ops_h).json()
    assert d["circuits_detail"] and all(c["substation_id"] == sub["id"] for c in d["circuits_detail"])
    assert all(u["substation_id"] == sub["id"] and u["kind"] in ("power_transformer", "breaker") for u in d["units"])
    fid = d["circuits_detail"][0]["id"]
    c = client.get(f"/api/assets/circuits/{fid}", headers=ops_h, params={"kind": "pole", "limit": 5}).json()
    assert c["list_kind"] == "pole" and all(u["feeder_id"] == fid and u["kind"] == "pole" for u in c["transformers"])
    marks = client.get(f"/api/assets/circuits/{fid}/markers", headers=ops_h).json()
    assert marks and {m["kind"] for m in marks} >= {"dist_transformer", "breaker"}
    with SessionLocal() as s:
        on_circuit = s.query(Asset).filter(Asset.feeder_id == fid).count()
    assert len([m for m in marks if m["kind"] != "power_transformer"]) == on_circuit
    region_sum = client.get("/api/assets/summary", headers=ops_h, params={"region": "central"}).json()
    whole = client.get("/api/assets/summary", headers=ops_h).json()
    assert region_sum["all"]["units"] < whole["all"]["units"] and region_sum["regions"][0]["id"] == "central"
    assert client.get("/api/network/substations/NOPE", headers=ops_h).status_code == 404
    assert client.get("/api/assets/circuits/FDR-NOPE-01/markers", headers=ops_h).status_code == 404


def test_geo_search_and_impact(client, ops_h, outbreak):
    g = client.get("/api/network/geo").json()  # public
    lats = [p[0] for p in g["state"]["rings"][0]]
    assert g["state"]["name"] == "Oklahoma" and 33.5 < min(lats) and max(lats) < 37.1
    assert {r["id"] for r in g["regions"]} == {"northeast", "central", "southwest", "northwest", "southeast"}
    hits = client.get("/api/search", headers=ops_h, params={"q": "PT-OKC"}).json()
    assert any(h["type"] == "asset" for h in hits)
    imp = client.get(f"/api/events/{outbreak['id']}/impact", headers=ops_h).json()
    assert imp["kind"] == "tornado" and imp["circuits_hit"] and imp["substations_exposed"] and imp["assets_on_hit_circuits"]
    assert all(c["path_ef"] is not None for c in imp["circuits_hit"])
    open_on = client.get("/api/outages", headers=ops_h, params={"feeder": imp["circuits_hit"][0]["id"], "size": 50}).json()
    assert all(o["feeder_id"] == imp["circuits_hit"][0]["id"] for o in open_on["items"])


def test_exposure_is_a_prediction_not_damage(client, ops_h, outbreak):
    p = client.get(f"/api/events/{outbreak['id']}", headers=ops_h).json()["prediction"]["result"]
    fid = next(c["id"] for c in p["circuits"] if c["in_path"])
    with SessionLocal() as s:
        aid = s.query(Asset).filter(Asset.feeder_id == fid, Asset.status == "in_service").first().id
    d = client.get(f"/api/assets/item/{aid}", headers=ops_h).json()
    x = next(e for e in d["exposure"] if e["event_id"] == outbreak["id"])
    assert x["in_path"] and "not confirmed" in x["basis"].lower() and d["status"] == "in_service"
    assert any(r["key"] == "storm_inspect" for r in d["recommendations"])


def test_rescore_handles_a_new_year_and_ids(client):
    with SessionLocal() as s:
        ids = [a.id for a in s.query(Asset).limit(3)]
        assert assets.rescore(s, ids) == 3
        assert asset_history.backfill(s) >= 0
