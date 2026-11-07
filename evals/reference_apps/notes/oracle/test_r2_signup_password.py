# reqs: R2
# hint: short passwords are accepted or valid ones rejected
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

def test_password_length_boundary():
    with client() as cl:
        assert cl.post("/auth/signup", json={"username": "p" + uuid.uuid4().hex[:8], "password": "1234567"}).status_code == 422
        assert cl.post("/auth/signup", json={"username": "q" + uuid.uuid4().hex[:8], "password": "12345678"}).status_code == 201
