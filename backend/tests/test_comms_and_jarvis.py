from datetime import datetime

from app.services import nhc

from .conftest import login


def test_message_approval_workflow(client, kyle):
    comms = login(client, "priya.nair")
    exec_ = login(client, "marcus.reed")
    d = client.post("/api/messages/ai-draft", headers=comms, json={"event_id": kyle["id"], "channel": "sms"}).json()
    assert "Kyle" in d["body"]
    m = client.post("/api/messages", headers=comms, json={"event_id": kyle["id"], "channel": "sms", "audience": "coastal",
                                                          "body": d["body"], "ai_generated": True, "submit": True}).json()
    assert m["status"] == "pending" and m["recipients"] > 0
    assert client.post(f"/api/messages/{m['id']}/reject", headers=exec_, json={"reason": "Add shelter info"}).json()["status"] == "rejected"
    client.patch(f"/api/messages/{m['id']}", headers=comms, json={"body": d["body"] + " Shelters: hcfl.example"})
    client.post(f"/api/messages/{m['id']}/submit", headers=comms)
    sent = client.post(f"/api/messages/{m['id']}/approve", headers=exec_).json()
    assert sent["status"] == "sent" and sent["approved_by"] == "Marcus Reed"
    assert client.post("/api/messages", headers=comms, json={"event_id": kyle["id"], "channel": "x", "body": "x" * 300}).status_code == 422
    assert client.post(f"/api/messages/{m['id']}/approve", headers=login(client, "luis.ortega")).status_code == 403


def test_jarvis_answers_from_live_data(client, ops_h, kyle):
    cases = {"Do I need more people?": "need more people", "When will Riverview be restored?": "Riverview",
             "What if it becomes a Cat 5?": "Category 5", "Give me a situation briefing": "Hurricane Kyle"}
    for q, expect in cases.items():
        r = client.post("/api/jarvis/ask", headers=ops_h, json={"question": q, "event_id": kyle["id"]}).json()
        assert expect in r["text"], (q, r["text"])
    assert len(client.get("/api/jarvis/messages", headers=ops_h).json()) == 1 + 2 * len(cases)


def test_assistant_conversations_and_saved_answers(client, kyle):
    h = login(client, "priya.nair")
    client.delete("/api/jarvis/messages", headers=h)
    first = client.post("/api/jarvis/ask", headers=h, json={"question": "Do I need more people?", "event_id": kyle["id"], "conversation_id": 0}).json()
    client.post("/api/jarvis/ask", headers=h, json={"question": "When will Riverview be restored?", "event_id": kyle["id"]})
    second = client.post("/api/jarvis/ask", headers=h, json={"question": "Where is the storm now?", "event_id": kyle["id"], "conversation_id": 0}).json()
    assert first["conversation_id"] != second["conversation_id"]
    convs = client.get("/api/jarvis/conversations", headers=h).json()
    assert [(c["title"], c["questions"]) for c in convs] == [("Where is the storm now?", 1), ("Do I need more people?", 2)]
    assert len(client.get("/api/jarvis/messages", headers=h, params={"conversation_id": first["conversation_id"]}).json()) == 5
    assert len(client.get("/api/jarvis/messages", headers=h, params={"conversation_id": 0}).json()) == 1  # greeting only

    assert client.put(f"/api/jarvis/messages/{first['id']}/saved", headers=h, json={"saved": True}).json()["saved"] is True
    saved = client.get("/api/jarvis/saved", headers=h).json()
    assert [(s["id"], s["question"]) for s in saved] == [(first["id"], "Do I need more people?")]
    assert client.put(f"/api/jarvis/messages/{first['id']}/saved", headers=login(client, "marcus.reed"), json={"saved": False}).status_code == 404

    assert client.delete(f"/api/jarvis/conversations/{first['conversation_id']}", headers=h).json()["ok"]
    assert [c["id"] for c in client.get("/api/jarvis/conversations", headers=h).json()] == [second["conversation_id"]]
    assert client.get("/api/jarvis/saved", headers=h).json() == []
    assert client.get("/api/jarvis/messages", headers=login(client, "marcus.reed"),
                      params={"conversation_id": second["conversation_id"]}).status_code == 404


def test_reports_have_history(client, ops_h):
    rows = client.get("/api/reports/events", headers=ops_h).json()
    closed = [r for r in rows if r["event"]["status"] == "closed"]
    assert len(closed) == 2 and all(r["etr_mae_h"] is not None and r["tickets"] > 50 for r in closed)
    detail = client.get(f"/api/reports/events/{closed[0]['event']['id']}", headers=ops_h).json()
    assert detail["zones"] and detail["channels"]


def test_nhc_feed_parsing():
    feed = {"activeStorms": [{"id": "al122026", "name": "Leah", "classification": "HU", "intensity": "100", "pressure": "962",
                              "latitudeNumeric": 24.1, "longitudeNumeric": -84.9, "movementDir": 30, "movementSpeed": 10,
                              "lastUpdate": "2026-10-03T15:00:00.000Z", "publicAdvisory": {"url": "https://www.nhc.noaa.gov/x"}}]}
    st = nhc.parse(feed)[0]
    assert st["wind_mph"] == 115 and st["category"] == 3 and st["movement"] == "NNE at 12 mph"
    track = nhc.project_track(st["lat"], st["lng"], st["heading_deg"], st["speed_mph"], datetime.fromisoformat(st["updated_at"]))
    assert track[0]["observed"] and track[-1]["lat"] > st["lat"]


def test_demo_refresh_tops_up_without_undoing_user_work(client, ops_h, kyle):
    exec_ = login(client, "marcus.reed")
    msgs = lambda: client.get("/api/messages", params={"event_id": kyle["id"]}, headers=ops_h).json()
    pending = [m for m in msgs() if m["status"] == "pending"]
    assert len(pending) == 2
    for m in pending:  # the user works through the approval queue
        assert client.post(f"/api/messages/{m['id']}/approve", headers=exec_).json()["status"] == "sent"
    added = client.post("/api/demo/refresh", headers=ops_h).json()
    assert added["messages"] == 2
    after = msgs()
    assert {m["id"] for m in pending} <= {m["id"] for m in after if m["status"] == "sent"}  # approvals kept
    new_pending = [m for m in after if m["status"] == "pending"]
    assert len(new_pending) == 2 and not {m["body"] for m in new_pending} & {m["body"] for m in pending}  # fresh wording
    assert client.post("/api/demo/refresh", headers=ops_h).json() == {"outages": 0, "messages": 0}  # already at the floor

    client.put("/api/admin/integrations", headers=login(client, "admin"), json={"connector_mode": "off"})
    for m in new_pending:
        client.post(f"/api/messages/{m['id']}/approve", headers=exec_)
    assert client.post("/api/demo/refresh", headers=ops_h).json() == {"outages": 0, "messages": 0}  # demo mode only
