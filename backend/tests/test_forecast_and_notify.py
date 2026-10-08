from datetime import timedelta

from app.db import SessionLocal
from app.models import Message, PublishedCircuitEtr
from app.services import connector

from .conftest import login
from .test_storm_workflow import activate


def test_prediction_has_circuit_and_region_etrs_with_ranges(client, ops_h, kyle):
    p = client.post(f"/api/events/{kyle['id']}/predictions", headers=ops_h, json={"category": 3, "save": False}).json()["result"]
    assert len(p["circuits"]) > 100 and {r["name"] for r in p["regions"]} == {"North", "Central", "East", "South Shore"}
    assert all(c["low_h"] < c["eta_h"] < c["high_h"] and c["region"] and c["substation"] for c in p["circuits"])
    assert sum(r["pred"] for r in p["regions"]) == sum(c["pred"] for c in p["circuits"])
    r = p["regions"][0]
    assert r["last_h"] == max(c["eta_h"] for c in p["circuits"] if c["region_id"] == r["id"])


def test_forecast_import_drives_the_prediction(client, ops_h, kyle):
    base = client.get(f"/api/events/{kyle['id']}/forecasts", headers=ops_h).json()
    assert base["latest"]["source"] and base["sample_csv"].startswith("zone,")  # demo storm has the parent model's forecast
    bad = client.post(f"/api/events/{kyle['id']}/forecasts", headers=ops_h, json={"csv": "zone,gust_mph\natlantis,120"})
    assert bad.status_code == 422 and "atlantis" in bad.json()["detail"]
    assert client.post(f"/api/events/{kyle['id']}/forecasts", headers=ops_h, json={"csv": "zone,gust_mph\ntpa,900"}).status_code == 422

    weak = "zone,gust_mph,surge_ft\n" + "\n".join(f"{z},70,0" for z in ("tpa", "tnc", "wch", "cwd", "ltz", "ttr", "brn", "val", "plc", "rvv", "apb", "rsk", "scc"))
    fc = client.post(f"/api/events/{kyle['id']}/forecasts", headers=ops_h, json={"csv": weak, "source": "Parent model run 12Z"}).json()
    assert fc["source"] == "Parent model run 12Z" and len(fc["zones"]) == 13
    weak_pred = client.get(f"/api/events/{kyle['id']}", headers=ops_h).json()["prediction"]["result"]
    assert weak_pred["forecast"]["source"] == "Parent model run 12Z" and weak_pred["zones"][0]["hazard"]["gust_mph"] == 70

    strong = client.post(f"/api/events/{kyle['id']}/forecasts", headers=ops_h,
                         json={"zones": [{"zone": "Tampa", "gust_mph": 160, "surge_ft": 12}]}).json()  # partial: others keep the advisory
    assert len(strong["zones"]) == 13 and sum(1 for z in strong["zones"] if z.get("filled")) == 12
    strong_pred = client.get(f"/api/events/{kyle['id']}", headers=ops_h).json()["prediction"]["result"]
    tpa = lambda p: next(z for z in p["zones"] if z["id"] == "tpa")["pred"]
    assert tpa(strong_pred) > tpa(weak_pred)
    # an explicit scenario ignores the forecast
    scen = client.post(f"/api/events/{kyle['id']}/predictions", headers=ops_h, json={"category": 2, "save": False}).json()["result"]
    assert scen["forecast"] is None and scen["scenario"] == "Cat 2"
    mock = client.post(f"/api/events/{kyle['id']}/forecasts", headers=ops_h, json={"mock": True}).json()
    assert len(mock["zones"]) == 13
    assert client.post(f"/api/events/{kyle['id']}/forecasts", headers=login(client, "priya.nair"), json={"mock": True}).status_code == 403


def test_publishing_circuits_texts_their_customers_and_updates_on_change(client, ops_h, kyle):
    activate(client, ops_h, kyle["id"], 40)
    c = client.get(f"/api/events/{kyle['id']}/etrs", headers=ops_h).json()["circuits"][0]
    client.post(f"/api/events/{kyle['id']}/publish/circuits", headers=ops_h, json={"feeder_ids": [c["id"]]})
    with SessionLocal() as s:
        sms = s.query(Message).filter(Message.audience == f"circuit:{c['id']}").all()
        assert len(sms) == 1 and sms[0].status == "sent" and c["id"] in sms[0].body and "confidence" in sms[0].body
        row = s.get(PublishedCircuitEtr, (kyle["id"], c["id"]))
        row.etr_at = row.etr_at - timedelta(hours=3)  # the live ETR has since moved 3 h later
        s.commit()
    connector.tick()
    with SessionLocal() as s:
        msgs = s.query(Message).filter(Message.audience == f"circuit:{c['id']}").order_by(Message.id).all()
        if any(o for o in client.get(f"/api/events/{kyle['id']}/etrs", headers=ops_h).json()["circuits"] if o["id"] == c["id"]):
            assert len(msgs) == 2 and "later" in msgs[-1].body


def test_region_and_circuit_audiences(client, ops_h, kyle):
    activate(client, ops_h, kyle["id"], 40)
    aud = {a["id"]: a for a in client.get("/api/comms/audiences", params={"event_id": kyle["id"]}, headers=ops_h).json()}
    assert {"region:north", "region:central", "region:east", "region:south", "circuits_published"} <= set(aud)
    circuit = next(k for k in aud if k.startswith("circuit:"))
    comms = login(client, "priya.nair")
    m = client.post("/api/messages", headers=comms, json={"event_id": kyle["id"], "channel": "sms", "audience": circuit,
                                                         "body": "Crews are on your circuit now."}).json()
    assert m["recipients"] == round(aud[circuit]["count"] * 0.71)
    m = client.post("/api/messages", headers=comms, json={"event_id": kyle["id"], "channel": "sms", "audience": "region:south", "body": "Hi"}).json()
    assert m["recipients"] > 0


def test_confidence_calibration_report(client, ops_h):
    r = client.get("/api/reports/calibration", headers=ops_h).json()
    assert r["snapshots"] > 100 and len(r["bands"]) >= 4 and r["window_h"] == 2
    assert all(0 <= b["actual_pct"] <= 100 and b["count"] for b in r["bands"])
    low, high = r["bands"][0], r["bands"][-1]
    assert high["actual_pct"] > low["actual_pct"]  # higher confidence really is right more often


def test_circuit_routes_and_gis_import(client, ops_h):
    r = client.get("/api/network/routes", headers=ops_h).json()
    assert r["counts"] == {"synthetic": len(r["feeders"])} and all(f["route"] and len(f["route"][0]) >= 2 for f in r["feeders"])
    admin = login(client, "admin")
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"CIRCUIT": "fdr-tpa-01", "Customers": "2500"},
         "geometry": {"type": "LineString", "coordinates": [[-82.47, 27.94], [-82.46, 27.95]]}},
        {"type": "Feature", "properties": {"feeder_id": "NOT-OURS"}, "geometry": {"type": "LineString", "coordinates": [[-82.4, 27.9], [-82.41, 27.91]]}}]}
    assert client.post("/api/admin/network/feeders", headers=ops_h, json=gj).status_code == 403
    res = client.post("/api/admin/network/feeders", headers=admin, json=gj).json()
    assert res["matched"] == 1 and res["unmatched_ids"] == ["NOT-OURS"]
    f = next(f for f in client.get("/api/network/routes", headers=ops_h).json()["feeders"] if f["id"] == "FDR-TPA-01")
    assert f["source"] == "imported" and f["route"] == [[[27.94, -82.47], [27.95, -82.46]]]
    projected = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"feeder_id": "FDR-TPA-02"},
                                                            "geometry": {"type": "LineString", "coordinates": [[540000, 1300000], [540100, 1300100]]}}]}
    bad = client.post("/api/admin/network/feeders", headers=admin, json=projected)
    assert bad.status_code == 422 and "EPSG:4326" in bad.json()["detail"]
    assert client.post("/api/admin/network/feeders/reset", headers=admin).json()["reset"] == len(r["feeders"])
    assert client.get("/api/network/routes", headers=ops_h).json()["counts"] == {"synthetic": len(r["feeders"])}
    assert all("route" in c for c in client.get("/api/public/outage-map").json()["circuits"])
