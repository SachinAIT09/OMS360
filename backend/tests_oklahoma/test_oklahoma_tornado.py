from app.db import SessionLocal
from app.models import Outage, StormEvent
from app.services import connector, ops
from app.services.prediction import predict

from .conftest import login


def _prediction(client, h, event_id, **body):
    return client.post(f"/api/events/{event_id}/predictions", headers=h, json={"save": False, **body}).json()["result"]


def test_profile_and_network_are_oklahoma(client, ops_h):
    p = client.get("/api/profile").json()  # public: the login page is branded with it
    assert p["territory"] == "oklahoma" and p["utility"] == "Prairie Sky Power" and p["timezone"] == "America/Chicago"
    assert p["hazard"] == "tornado" and "Tornado" in p["event_kinds"]
    with SessionLocal() as s:
        idx = ops.network_index(s)
    assert {f["region"] for f in idx.values()} == {"Northeast", "Central", "Southwest", "Northwest", "Southeast"}
    zones = {z["short"] for z in client.get("/api/reference", headers=ops_h).json()["zones"]}
    assert {"Tulsa", "Oklahoma City", "Moore", "Lawton"} <= zones


def test_demo_event_is_a_tornado_with_paths(client, ops_h, outbreak):
    assert outbreak["kind"] == "Tornado" and outbreak["hazard"] == "tornado" and outbreak["category"] == 4
    assert {p["path"] for p in outbreak["track"]} == {0, 1} and all(p["width_m"] for p in outbreak["track"])


def test_tornado_prediction_is_built_from_circuits(client, ops_h, outbreak):
    p = _prediction(client, ops_h, outbreak["id"])
    assert p["kind"] == "tornado" and p["surge"] is None and p["boil_water_zones"] == []
    circuits = p["circuits"]
    hit = [c for c in circuits if c["in_path"]]
    far = [c for c in circuits if c["path_km"] is not None and c["path_km"] > 60]
    assert hit and far
    assert min(c["pct"] for c in hit) > 5 * max(c["pct"] for c in far)  # damage follows the path, not the zone
    assert min(c["eta_h"] for c in hit) > max(c["eta_h"] for c in far)  # in-path circuits are rebuilt
    for z in p["zones"]:  # zones are the sums of their circuits
        assert z["pred"] == sum(c["pred"] for c in circuits if c["zone_id"] == z["id"])
    assert p["circuits_in_path"] == len(hit) and sum(x["circuits_hit"] for x in p["paths"]) == len(hit)
    # two circuits out of the same zone can see very different damage
    moore = [c for c in circuits if c["zone_id"] == "moo"]
    assert max(c["pct"] for c in moore) > 0.5
    assert {"Northeast", "Central"} <= {r["name"] for r in p["regions"] if r["circuits_in_path"]}


def test_ef_rating_scales_the_prediction(client, ops_h, outbreak):
    totals = [_prediction(client, ops_h, outbreak["id"], category=c)["pred_total"] for c in (1, 3, 5)]
    assert totals[0] < totals[1] < totals[2]


def test_tornado_tickets_follow_the_paths(client, ops_h, outbreak):
    client.post(f"/api/events/{outbreak['id']}/status", headers=ops_h, json={"status": "active"})
    for _ in range(30):
        connector.tick()
    with SessionLocal() as s:
        e = s.get(StormEvent, outbreak["id"])
        p = predict(s, e)
        in_path = {c["id"] for c in p["circuits"] if c["in_path"]}
        tickets = s.query(Outage).filter(Outage.event_id == e.id, Outage.reported_at >= e.activated_at).all()
    assert tickets
    on_path = [t for t in tickets if t.feeder_id in in_path]
    assert len(on_path) > len(tickets) / 2
    assert any(t.cause == "tornado" for t in on_path)


def test_tornado_wording_in_comms_recommendations_and_jarvis(client, ops_h, outbreak):
    eid = outbreak["id"]
    for purpose in ("prepare", "warning", "outage"):
        d = client.post("/api/messages/ai-draft", headers=ops_h, json={"event_id": eid, "channel": "sms", "purpose": purpose}).json()
        assert "Prairie Sky" in d["body"] and "landfall" not in d["body"].lower() and "surge" not in d["body"].lower()
    recs = client.get(f"/api/events/{eid}/recommendations", headers=ops_h).json()
    keys = {r["key"] for r in recs}
    assert {"tornado_logistics", "xfmr_prestage"} <= keys
    assert not any("surge" in (r["detail"] + r["why"]).lower() or "landfall" in (r["detail"] + r["why"]).lower() for r in recs)
    ask = lambda q: client.post("/api/jarvis/ask", headers=ops_h, json={"question": q, "event_id": eid}).json()
    assert "circuits** are on the forecast damage paths" in ask("Which circuits are in the tornado path?")["text"]
    assert "EF5" in ask("What if it's an EF5?")["text"]
    assert "Central region" in ask("Oldest transformers in the Central region")["text"]
    assert "Central region" in ask("What are the ETRs in the Central region?")["text"]


def test_create_tornado_event_with_a_path(client, ops_h):
    e = client.post("/api/events", headers=ops_h, json={"name": "Lawton tornado", "kind": "Tornado", "category": 3, "lat": 34.55,
                                                       "lng": -98.5, "heading_deg": 45, "path_length_mi": 12, "path_width_m": 600}).json()
    assert e["hazard"] == "tornado" and len(e["track"]) >= 3 and e["track"][0]["width_m"] == 600
    p = _prediction(client, ops_h, e["id"])
    lawton = [z for z in p["zones"] if z["id"] == "law"][0]
    assert lawton["pred"] > 0 and lawton["circuits_in_path"] > 0
    assert client.post("/api/events", headers=login(client, "priya.nair"), json={"name": "x", "kind": "Tornado"}).status_code == 403
