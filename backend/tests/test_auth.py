from .conftest import login


def test_login_and_me(client):
    assert client.post("/api/auth/login", json={"email": "dana.whitaker@bayviewpw.example", "password": "nope"}).status_code == 401
    h = login(client)
    me = client.get("/api/auth/me", headers=h).json()
    assert me["role"] == "ops_manager" and "events.manage" in me["permissions"]
    assert client.get("/api/events").status_code == 401
    client.post("/api/auth/logout", headers=h)
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_role_guards(client, kyle):
    dispatcher = login(client, "luis.ortega")
    comms = login(client, "priya.nair")
    assert client.post("/api/events", headers=comms, json={"name": "Test"}).status_code == 403
    recs = client.get(f"/api/events/{kyle['id']}/recommendations", headers=dispatcher).json()
    assert client.post(f"/api/recommendations/{recs[0]['id']}/approve", headers=dispatcher).status_code == 403
    assert client.get("/api/admin/users", headers=dispatcher).status_code == 403
    assert client.get("/api/admin/users", headers=login(client, "admin")).status_code == 200


def test_powerconnect_demo_login(client):
    r = client.post("/api/auth/login", json={"email": "steve@powerconnect.ai", "password": "admin"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
