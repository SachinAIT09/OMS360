"""Regression tests for the P1 issues found in the end-to-end audit."""
from app.db import SessionLocal
from app.models import Outage
from app.services import connector

from .conftest import login
from .test_storm_workflow import activate


def test_p1_3_event_cannot_close_with_open_outages(client, ops_h, kyle):
    activate(client, ops_h, kyle["id"], 15)
    client.post(f"/api/events/{kyle['id']}/status", headers=ops_h, json={"status": "restoring"})
    r = client.post(f"/api/events/{kyle['id']}/status", headers=ops_h, json={"status": "closed"})
    assert r.status_code == 409 and "still open" in r.json()["detail"]
    with SessionLocal() as s:
        for o in s.query(Outage).filter(Outage.event_id == kyle["id"], Outage.status.in_(["reported", "assessed", "assigned", "in_progress"])):
            o.status = "cancelled"
        s.commit()
    assert client.post(f"/api/events/{kyle['id']}/status", headers=ops_h, json={"status": "closed"}).json()["status"] == "closed"


def test_p1_1_published_circuit_told_when_power_is_back(client, ops_h, kyle):
    activate(client, ops_h, kyle["id"], 30)
    c = client.get(f"/api/events/{kyle['id']}/etrs", headers=ops_h).json()["circuits"][0]
    client.post(f"/api/events/{kyle['id']}/publish/circuits", headers=ops_h, json={"feeder_ids": [c["id"]]})
    with SessionLocal() as s:
        for o in s.query(Outage).filter(Outage.event_id == kyle["id"], Outage.feeder_id == c["id"], Outage.status.in_(["reported", "assessed", "assigned", "in_progress"])):
            o.status = "restored"
        s.commit()
    connector.tick()
    connector.tick()  # a second pass must not text again
    comms = login(client, "priya.nair")
    msgs = [m for m in client.get("/api/messages", params={"event_id": kyle["id"]}, headers=comms).json() if m["audience"] == f"circuit:{c['id']}"]
    restored = [m for m in msgs if "restored" in m["body"].lower()]
    assert len(restored) == 1 and "Reply OUT" in restored[0]["body"] and restored[0]["status"] == "sent"
    # a new outage on the restored circuit re-arms it: customers get the new ETR
    with SessionLocal() as s:
        o = s.query(Outage).filter(Outage.event_id == kyle["id"], Outage.feeder_id == c["id"]).first()
        s.add(Outage(number="OUT-QA-1", event_id=kyle["id"], zone_id=o.zone_id, feeder_id=c["id"], device="Pole P-1", cause="tree",
                     damage="pole", customers=120, priority="normal", source="AMI", lat=o.lat, lng=o.lng))
        s.commit()
    connector.tick()
    msgs = [m for m in client.get("/api/messages", params={"event_id": kyle["id"]}, headers=comms).json() if m["audience"] == f"circuit:{c['id']}"]
    assert any("New outage on your circuit" in m["body"] for m in msgs)


def test_p1_2_resource_planning_by_region(client, ops_h, kyle):
    p = client.post(f"/api/events/{kyle['id']}/predictions", headers=ops_h, json={"category": 3, "save": False}).json()["result"]
    regions = p["regions"]
    assert all(r["line_workers"] > 0 and r["tree_workers"] > 0 for r in regions)
    assert abs(sum(r["line_workers"] for r in regions) - p["required"]["line"]) <= len(regions)  # same 185-customers-per-worker rule
    biggest = max(regions, key=lambda r: r["pred"])
    assert biggest["line_workers"] == max(r["line_workers"] for r in regions)
    # live: crews working and work waiting per region
    activate(client, ops_h, kyle["id"], 30)
    net = client.get(f"/api/events/{kyle['id']}/etrs", headers=ops_h).json()
    assert all({"crews", "waiting", "backlog_h"} <= set(r) for r in net["regions"])
    waiting_before = sum(r["waiting"] for r in net["regions"])
    assert waiting_before > 0
    client.post(f"/api/events/{kyle['id']}/auto-dispatch", headers=login(client, "luis.ortega"))
    after = client.get(f"/api/events/{kyle['id']}/etrs", headers=ops_h).json()["regions"]
    assert sum(r["crews"] for r in after) > sum(r["crews"] for r in net["regions"]) and sum(r["waiting"] for r in after) < waiting_before
