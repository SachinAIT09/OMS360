import os
import tempfile

import pytest

os.environ["OMS360_DB"] = os.path.join(tempfile.mkdtemp(), "test-oklahoma.sqlite")
os.environ["OMS360_DISABLE_CONNECTOR"] = "1"
os.environ["OMS360_TERRITORY"] = "oklahoma"
os.environ.setdefault("OMS360_ASSET_DENSITY", "150")  # a sparse transformer register keeps per-test seeding fast

from fastapi.testclient import TestClient  # noqa: E402

from app.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

DOMAIN = "prairieskypower.example"


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    init_db()
    with TestClient(app) as c:
        yield c


def login(client, who="dana.whitaker"):
    r = client.post("/api/auth/login", json={"email": f"{who}@{DOMAIN}", "password": "oms360"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def ops_h(client):
    return login(client, "dana.whitaker")


@pytest.fixture()
def outbreak(client, ops_h):
    return client.get("/api/events/current", headers=ops_h).json()
