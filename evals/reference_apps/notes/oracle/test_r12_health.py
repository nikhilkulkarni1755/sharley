# reqs: R12
# hint: health check does not return 200
import os
import uuid

import httpx

BASE = os.environ["BASE_URL"]


def client():
    return httpx.Client(base_url=BASE, timeout=10)


def new_user(cl, password="password123"):
    name = "u" + uuid.uuid4().hex[:10]
    assert cl.post("/auth/signup", json={"username": name, "password": password}).status_code == 201
    token = cl.post("/auth/login", json={"username": name, "password": password}).json()["token"]
    return name, {"Authorization": "Bearer " + token}


def add_note(cl, auth, title="t", body="b"):
    r = cl.post("/notes", json={"title": title, "body": body}, headers=auth)
    assert r.status_code == 201
    return r.json()["id"]

def test_health_ok():
    with client() as cl:
        r = cl.get("/health")
        assert r.status_code == 200 and r.json() == {"status": "ok"}
