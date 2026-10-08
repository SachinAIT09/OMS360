from app.db import SessionLocal
from app.models import Feeder, Outage, StormEvent
from app.services import ops

from .conftest import login
from .test_storm_workflow import activate


def test_network_hierarchy_is_seeded(client):
    with SessionLocal() as s:
        idx = ops.network_index(s)
    assert idx and all(f["substation_id"] and f["region_id"] for f in idx.values())
    assert {f["region"] for f in idx.values()} == {"North", "Central", "East", "South Shore"}


def test_circuit_and_region_etrs(client, ops_h, kyle):
    activate(client, ops_h, kyle["id"], 40)
    net = client.get(f"/api/events/{kyle['id']}/etrs", headers=ops_h).json()
    circuits, regions = net["circuits"], net["regions"]
    with SessionLocal() as s:
        open_feeders = {o.feeder_id for o in s.query(Outage).filter(Outage.event_id == kyle["id"], Outage.status.in_(ops.OPEN))}
    assert {c["id"] for c in circuits} == open_feeders
    assert all(30 <= c["confidence"] <= 95 and c["etr_at"] and c["region"] and c["substation"] for c in circuits)
    assert sum(r["customers_out"] for r in regions) == sum(c["customers_out"] for c in circuits)
    busiest = max(regions, key=lambda r: r["customers_out"])
    assert busiest["etr_at"] == max(c["etr_at"] for c in circuits if c["region_id"] == busiest["id"])
    only = client.get(f"/api/events/{kyle['id']}/etrs", params={"region": busiest["id"]}, headers=ops_h).json()["circuits"]
    assert only and all(c["region_id"] == busiest["id"] for c in only)


def test_confidence_rises_as_work_is_committed(client, ops_h, kyle):
    activate(client, ops_h, kyle["id"], 40)
    before = {c["id"]: c["confidence"] for c in client.get(f"/api/events/{kyle['id']}/etrs", headers=ops_h).json()["circuits"]}
    with SessionLocal() as s:
        e = s.get(StormEvent, kyle["id"])
        fid = next(iter(before))
        for o in s.query(Outage).filter(Outage.event_id == e.id, Outage.feeder_id == fid, Outage.status.in_(ops.OPEN)):
            o.status, o.damage = "in_progress", "conductor" if o.damage == "unknown" else o.damage
        s.commit()
    after = {c["id"]: c["confidence"] for c in client.get(f"/api/events/{kyle['id']}/etrs", headers=ops_h).json()["circuits"]}
    assert after[fid] >= before[fid]


def test_publish_by_confidence_and_public_circuit_lookup(client, ops_h, kyle):
    assert client.post(f"/api/events/{kyle['id']}/publish/circuits", headers=ops_h, json={}).status_code == 409
    activate(client, ops_h, kyle["id"], 40)
    circuits = client.get(f"/api/events/{kyle['id']}/etrs", headers=ops_h).json()["circuits"]
    bar = sorted(c["confidence"] for c in circuits)[len(circuits) // 2]
    eligible = {c["id"] for c in circuits if c["confidence"] >= bar}
    r = client.post(f"/api/events/{kyle['id']}/publish/circuits", headers=ops_h, json={"min_confidence": bar}).json()
    assert r["published"] == len(eligible)
    published = {c["id"] for c in client.get(f"/api/events/{kyle['id']}/etrs", headers=ops_h).json()["circuits"] if c["published"]}
    assert published == eligible
    assert client.post(f"/api/events/{kyle['id']}/publish/circuits", headers=login(client, "priya.nair"), json={}).status_code == 403

    # public lookup: the address's own circuit ETR once that circuit is published, else the zone fallback
    look = client.get("/api/public/lookup", params={"address": "1208 Bayshore Blvd, Tampa"}).json()
    fid = look["circuit"]
    client.post(f"/api/events/{kyle['id']}/publish/circuits", headers=ops_h, json={"feeder_ids": [fid]})
    look = client.get("/api/public/lookup", params={"address": "1208 Bayshore Blvd, Tampa"}).json()
    open_on_circuit = any(c["id"] == fid for c in client.get(f"/api/events/{kyle['id']}/etrs", headers=ops_h).json()["circuits"])
    if open_on_circuit:
        assert look["status"] == "etr" and look["level"] == "circuit" and look["confidence"]
    else:
        assert look.get("level") != "circuit"
    client.delete(f"/api/events/{kyle['id']}/publish/circuits/{fid}", headers=ops_h)
    assert client.get("/api/public/lookup", params={"address": "1208 Bayshore Blvd, Tampa"}).json().get("level") != "circuit"


def test_circuit_recommendation_and_jarvis(client, ops_h, kyle):
    activate(client, ops_h, kyle["id"], 40)
    recs = client.get(f"/api/events/{kyle['id']}/recommendations", headers=ops_h).json()
    rec = next((r for r in recs if r["key"] == "publish_circuit_etrs" and r["status"] == "open"), None)
    if rec:
        assert "published" in client.post(f"/api/recommendations/{rec['id']}/approve", headers=ops_h).json()["outcome"]
    c = client.get(f"/api/events/{kyle['id']}/etrs", headers=ops_h).json()["circuits"][0]
    r = client.post("/api/jarvis/ask", headers=ops_h, json={"question": f"When will circuit {c['id']} be restored?", "event_id": kyle["id"]}).json()
    assert c["id"] in r["text"] and "confidence" in r["text"]
    r = client.post("/api/jarvis/ask", headers=ops_h, json={"question": f"ETRs in the {c['region']} region?", "event_id": kyle["id"]}).json()
    assert f"{c['region']} region" in r["text"]


def test_report_has_etr_accuracy_by_region_and_circuit(client, ops_h):
    closed = [r for r in client.get("/api/reports/events", headers=ops_h).json() if r["event"]["status"] == "closed"]
    acc = client.get(f"/api/reports/events/{closed[0]['event']['id']}", headers=ops_h).json()["etr_accuracy"]
    assert len(acc["regions"]) == 4 and acc["circuits"]
    assert all(r["mae_h"] >= 0 and 0 <= r["within_2h_pct"] <= 100 for r in acc["regions"] + acc["circuits"])
    with SessionLocal() as s:
        assert s.get(Feeder, acc["circuits"][0]["name"]) is not None


def test_rain_demo_has_circuit_etrs_to_show(client, ops_h):
    events = client.get("/api/events", headers=ops_h).json()
    rain = next(e for e in events if e["name"] == "Tampa Bay Rain Event")
    assert rain["kind"] == "Rain Event" and rain["status"] == "restoring"
    assert client.get("/api/events/current", headers=ops_h).json()["name"] == "Hurricane Kyle"
    net = client.get(f"/api/events/{rain['id']}/etrs", headers=ops_h).json()
    conf = [c["confidence"] for c in net["circuits"]]
    assert len(conf) > 20 and min(conf) < 70 <= max(conf) and any(c["published"] for c in net["circuits"])
    assert all(r["circuits_out"] for r in net["regions"])
    assert client.get("/api/public/outage-map").json()["event"]["name"] == "Tampa Bay Rain Event"
