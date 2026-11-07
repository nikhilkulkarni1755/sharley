# reqs: R3
# hint: login does not behave correctly for right and wrong passwords
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

def test_login_success_and_failure_codes():
    with client() as cl:
        name, _ = new_user(cl)
        ok = cl.post("/auth/login", json={"username": name, "password": "password123"})
        assert ok.status_code == 200 and ok.json()["token"]
        assert cl.post("/auth/login", json={"username": name, "password": "wrongpass1"}).status_code == 401
        assert cl.post("/auth/login", json={"username": "nobody" + uuid.uuid4().hex[:6], "password": "x"}).status_code == 401
