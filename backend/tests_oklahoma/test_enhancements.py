from datetime import datetime, timezone

from app.db import SessionLocal
from app.fmt import fmt_dt
from app.models import Outage
from app.services import nws, ops


def test_customer_messages_use_local_time():
    assert fmt_dt(datetime(2026, 10, 20, 2, 0, tzinfo=timezone.utc)) == "Mon, Oct 19, 9:00 PM"  # Central daylight time


def test_aging_transformers_lengthen_transformer_jobs():
    o = Outage(damage="transformer", cause="wind")
    assert ops.job_hours(o, 0.5) > ops.job_hours(o, 0.0) == ops.JOB_HOURS["transformer"]
    service = Outage(damage="service", cause="wind")
    assert ops.job_hours(service, 0.5) == ops.job_hours(service, 0.0)


def test_nws_warning_parsing():
    a = nws.parse(nws.sample_feed())[0]
    assert a["event"] == "Tornado Warning" and a["importable"] and a["ef_estimate"] == 3  # observed + considerable threat
    assert a["motion"]["heading_deg"] == 50 and a["motion"]["speed_mph"] == 35  # from 230° at 30 kt → toward 50°
    p = nws.warning_path(a)
    assert p["ef"] == 3 and len(p["points"]) > 2 and p["points"][-1][0] > p["points"][0][0]  # heads north-east
    assert nws.ef_estimate({"tornadoDamageThreat": ["CATASTROPHIC"]}) == 4 and nws.ef_estimate({"tornadoDetection": ["RADAR INDICATED"]}) == 1


def test_import_warning_and_replace_with_survey(client, ops_h):
    e = client.post("/api/events/import-nws", headers=ops_h, json={"sample": True}).json()
    assert e["kind"] == "Tornado" and e["source"] == "nws" and e["category"] == 3 and len(e["track"]) > 2
    planned = client.get(f"/api/events/{e['id']}", headers=ops_h).json()["prediction"]["result"]
    assert planned["kind"] == "tornado" and planned["circuits_in_path"] > 0

    # the survey puts the tornado somewhere else entirely: through Lawton, EF2
    csv = "path,ef,width_m,lat,lng\n1,2,500,34.56,-98.47\n1,2,500,34.62,-98.36\n1,2,500,34.66,-98.30"
    r = client.put(f"/api/events/{e['id']}/paths", headers=ops_h, json={"csv": csv, "surveyed": True}).json()
    assert r["category"] == 2 and all(p["observed"] for p in r["track"])
    surveyed = client.get(f"/api/events/{e['id']}", headers=ops_h).json()["prediction"]["result"]
    hit = {c["zone_id"] for c in surveyed["circuits"] if c["in_path"]}
    assert hit == {"law"} and "surveyed paths" in surveyed["scenario"]
    assert client.put(f"/api/events/{e['id']}/paths", headers=ops_h, json={"csv": "lat,lng\n1,2"}).status_code == 422
    kyle_like = client.post("/api/events", headers=ops_h, json={"name": "Ice", "kind": "Winter Storm"}).json()
    assert client.put(f"/api/events/{kyle_like['id']}/paths", headers=ops_h, json={"csv": csv}).status_code == 409


def test_replacement_plan(client, ops_h):
    small = client.get("/api/assets/plan", headers=ops_h, params={"budget": 2e6}).json()
    big = client.get("/api/assets/plan", headers=ops_h, params={"budget": 30e6}).json()
    assert 0 < small["cost"] <= 2e6 and big["cost"] <= 30e6 and big["units"] > small["units"]
    assert 0 < small["risk_reduced_pct"] < big["risk_reduced_pct"] < 1
    now, later = big["projection"][0], big["projection"][-1]
    assert later["no_action"]["expected_failures"] > now["no_action"]["expected_failures"]  # an untouched fleet ages
    assert all(x["with_plan"]["risk"] <= x["no_action"]["risk"] for x in big["projection"])
    gains = [i["risk_reduced"] for i in big["items"]]
    assert gains == sorted(gains, reverse=True)
    f = [x["risk_reduced_pct"] for x in big["frontier"]]
    assert f == sorted(f)
    central = client.get("/api/assets/plan", headers=ops_h, params={"budget": 10e6, "region": "central"}).json()
    assert central["units"] and {r["name"] for r in central["by_region"]} == {"Central"}
    dist = client.get("/api/assets/plan", headers=ops_h, params={"budget": 1e6, "kind": "dist_transformer"}).json()
    assert dist["by_kind"]["power_transformer"] == 0 and dist["units"] > 0


def test_live_circuit_etrs_show_transformer_health(client, ops_h):
    rain = next(e for e in client.get("/api/events", headers=ops_h).json() if e["status"] == "restoring")
    circuits = client.get(f"/api/events/{rain['id']}/etrs", headers=ops_h).json()["circuits"]
    assert circuits and all(c["asset_hi"] is not None for c in circuits)
    with SessionLocal() as s:
        o = s.query(Outage).filter(Outage.event_id == rain["id"], Outage.status.in_(ops.OPEN)).first()
        assert ops.ticket_hours(s, o) >= ops.job_hours(o)


def test_every_open_storm_gets_sample_comms_that_persist(client, ops_h):
    """A storm opened later (e.g. a new NWS warning) gets the sample campaign on the next app load; it lives in the database, so
    refreshing and restarting keep it, and what people did to the messages is never undone."""
    from app.db import init_db

    e = client.post("/api/events", headers=ops_h, json={"name": "Lawton tornado", "kind": "Tornado", "category": 2, "lat": 34.55,
                                                       "lng": -98.5}).json()
    msgs = lambda: client.get(f"/api/messages?event_id={e['id']}", headers=ops_h).json()
    assert msgs() == []
    assert client.post("/api/demo/refresh", headers=ops_h).json()["messages"] >= 12
    first = msgs()
    assert {m["status"] for m in first} >= {"sent", "pending", "scheduled", "draft", "rejected"}
    pending = next(m for m in first if m["status"] == "pending")
    assert client.post(f"/api/messages/{pending['id']}/approve", headers=ops_h).status_code == 200

    client.post("/api/demo/refresh", headers=ops_h)  # page refresh
    init_db()  # server restart
    after = {m["id"]: m for m in msgs()}
    assert {m["id"] for m in first} <= after.keys()  # nothing was deleted
    assert after[pending["id"]]["status"] in ("sent", "scheduled")  # the approval stuck
    assert sum(m["status"] == "pending" for m in after.values()) >= 2  # and the queue was topped back up
    assert client.post("/api/demo/refresh", headers=ops_h).json()["messages"] == 0  # stable: nothing more to add
