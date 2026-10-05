from datetime import datetime

from app.db import SessionLocal
from app.models import Crew
from app.services import connector

from .conftest import login

ADDRESSES = {"tpa": "1208 Bayshore Blvd, Tampa", "brn": "455 Lumsden Rd, Brandon", "apb": "6301 Apollo Beach Blvd, Apollo Beach",
             "rvv": "10920 Big Bend Rd, Riverview", "scc": "1802 Cortaro Dr, Sun City Center", "plc": "3305 James L Redman Pkwy, Plant City"}


def activate(client, h, event_id, ticks=15):
    client.post(f"/api/events/{event_id}/status", headers=h, json={"status": "active"})
    for _ in range(ticks):
        connector.tick()


def test_event_lifecycle(client, ops_h):
    e = client.post("/api/events", headers=ops_h, json={"name": "Hurricane Test", "category": 2}).json()
    assert e["status"] == "monitoring" and len(e["track"]) > 3
    assert client.post(f"/api/events/{e['id']}/status", headers=ops_h, json={"status": "restoring"}).status_code == 409
    for st in ("preparing", "active", "restoring", "closed"):
        assert client.post(f"/api/events/{e['id']}/status", headers=ops_h, json={"status": st}).json()["status"] == st
    tl = client.get(f"/api/events/{e['id']}/timeline", headers=ops_h).json()
    assert any("Restoring → Closed" in a["detail"] for a in tl)


def test_prediction_and_mutual_aid_recommendation(client, ops_h, kyle):
    run = client.post(f"/api/events/{kyle['id']}/predictions", headers=ops_h, json={"category": 4}).json()
    assert run["result"]["pred_total"] > 300000
    recs = client.get(f"/api/events/{kyle['id']}/recommendations", headers=ops_h).json()
    ma = next(r for r in recs if r["key"] == "mutual_aid" and r["status"] == "open")
    r = client.post(f"/api/recommendations/{ma['id']}/approve", headers=ops_h).json()
    assert r["status"] == "approved" and "requests" in r["outcome"]
    assert len(client.get("/api/mutual-aid", params={"event_id": kyle["id"]}, headers=ops_h).json()) >= 3
    assert client.post(f"/api/recommendations/{ma['id']}/approve", headers=ops_h).status_code == 409
    again = client.post(f"/api/events/{kyle['id']}/predictions", headers=ops_h, json={"category": 4}).json()
    assert again["result"]["needed"]["line"] == 0  # gap closed by the requests


def test_mutual_aid_arrival_rosters_crews(client, ops_h, kyle):
    req = client.post("/api/mutual-aid", headers=ops_h, json={"event_id": kyle["id"], "company": "Test Power Co", "workers": 40}).json()
    for st in ("confirmed", "en_route", "arrived"):
        assert client.post(f"/api/mutual-aid/{req['id']}/status", headers=ops_h, json={"status": st}).json()["status"] == st
    crews = client.get("/api/crews", params={"source": "mutual_aid"}, headers=ops_h).json()
    assert len(crews) == 10 and all(c["status"] == "staged" for c in crews)


def test_live_outages_dispatch_and_restore(client, ops_h, kyle):
    activate(client, ops_h, kyle["id"])
    page = client.get("/api/outages", params={"event_id": kyle["id"], "size": 100}, headers=ops_h).json()
    assert page["total"] > 0 and all(o["etr_at"] for o in page["items"])
    disp = login(client, "luis.ortega")
    assert client.post(f"/api/events/{kyle['id']}/auto-dispatch", headers=disp).json()["dispatched"] > 0
    t = client.get("/api/outages", params={"event_id": kyle["id"], "status": "assigned"}, headers=disp).json()["items"][0]
    d = client.post(f"/api/outages/{t['id']}/status", headers=disp, json={"status": "in_progress"}).json()
    assert d["status"] == "in_progress" and d["etr_committed"]
    d = client.post(f"/api/outages/{t['id']}/status", headers=disp, json={"status": "restored"}).json()
    assert d["status"] == "restored" and d["restored_at"]
    assert client.post(f"/api/outages/{t['id']}/status", headers=disp, json={"status": "assigned"}).status_code == 409
    stats = client.get(f"/api/events/{kyle['id']}/overview", headers=ops_h).json()["stats"]
    assert stats["customers_affected"] > stats["customers_out"]


def test_more_crews_bring_etr_forward(client, ops_h, kyle):
    with SessionLocal() as s:
        for c in s.query(Crew).all():
            c.status = "off_shift"
        s.commit()
    activate(client, ops_h, kyle["id"], 10)

    def last_etr():
        return datetime.fromisoformat(client.get(f"/api/events/{kyle['id']}/restoration", headers=ops_h).json()["stats"]["last_etr_at"])

    before = last_etr()
    with SessionLocal() as s:
        for c in s.query(Crew).filter(Crew.kind == "line").all():
            c.status = "available"
        s.commit()
    assert last_etr() < before


def test_publish_gate_and_public_lookup(client, ops_h, kyle):
    assert client.post(f"/api/events/{kyle['id']}/publish", headers=ops_h, json={}).status_code == 409
    activate(client, ops_h, kyle["id"], 40)
    zones = client.get(f"/api/events/{kyle['id']}/restoration", headers=ops_h).json()["stats"]["zones"]
    zone = next((z for z in zones if z["open_tickets"] and z["id"] in ADDRESSES), None) or next(z for z in zones if z["open_tickets"])
    addr = ADDRESSES.get(zone["id"], zone["short"])
    look = client.get("/api/public/lookup", params={"address": addr}).json()  # public, no sign-in
    assert look["status"] == "confirmed" and "etr_at" not in look
    client.post(f"/api/events/{kyle['id']}/publish", headers=ops_h, json={"zone_ids": [zone["id"]]})
    look = client.get("/api/public/lookup", params={"address": addr}).json()
    assert look["status"] == "etr" and look["etr_at"]
    assert sum(1 for z in client.get("/api/public/outage-map").json()["zones"] if z["etr_at"]) == 1


def test_preparing_storm_keeps_a_live_trickle_of_work(client, ops_h, monkeypatch):
    e = client.post("/api/events", headers=ops_h, json={"name": "Hurricane Trickle", "category": 2}).json()
    client.post(f"/api/events/{e['id']}/status", headers=ops_h, json={"status": "preparing"})
    monkeypatch.setattr(connector, "BAND_NEW_CHANCE", 1.0)
    monkeypatch.setattr(connector, "BAND_DISPATCH_CHANCE", 1.0)
    for _ in range(40):
        connector.tick()
    items = client.get("/api/outages", params={"event_id": e["id"], "size": 100}, headers=ops_h).json()["items"]
    open_ = [o for o in items if o["status"] != "restored"]
    assert 0 < len(open_) <= connector.BAND_OPEN_TARGET
    assert any(o["status"] in ("assigned", "in_progress") for o in items)  # routine dispatch put crews on it
    assert all(o["customers"] <= 900 for o in items)  # scattered band outages, not the main storm
