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


def test_gmail_admin_login_and_protection(client):
    r = client.post("/api/auth/login", json={"email": " Admin@Gmail.com ", "password": "admin@123"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
    steve = {"Authorization": f"Bearer {client.post('/api/auth/login', json={'email': 'steve@powerconnect.ai', 'password': 'admin'}).json()['token']}"}
    uid = r.json()["user"]["id"]
    for patch in ({"active": False}, {"role": "dispatcher"}, {"password": "changed1"}):
        assert client.patch(f"/api/admin/users/{uid}", headers=steve, json=patch).status_code == 409
    assert client.patch(f"/api/admin/users/{uid}", headers=steve, json={"title": "Demo admin"}).status_code == 200


def test_demo_admin_heals_on_startup(client):
    from sqlalchemy import select
    from app.auth import hash_password
    from app.db import SessionLocal, init_db
    from app.models import User
    with SessionLocal() as s:
        u = s.scalars(select(User).where(User.email == "admin@gmail.com")).one()
        u.active, u.role, u.password_hash = False, "comms", hash_password("something-else")
        s.commit()
    assert client.post("/api/auth/login", json={"email": "admin@gmail.com", "password": "admin@123"}).status_code == 401
    init_db()
    r = client.post("/api/auth/login", json={"email": "admin@gmail.com", "password": "admin@123"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"


def test_session_survives_database_rebuild(client):
    """Free hosting wipes the database on restart; a signed token must keep working after the reseed."""
    from app.db import engine, init_db
    from app.models import Base
    h = login(client, "admin")
    Base.metadata.drop_all(engine)
    init_db()
    assert client.get("/api/auth/me", headers=h).status_code == 200


def test_tampered_token_rejected(client):
    token = login(client)["Authorization"][7:]
    payload, sig = token.split(".")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {payload}.{sig[::-1]}"}).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
