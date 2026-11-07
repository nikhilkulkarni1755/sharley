# reqs: R4
# hint: repeated failed logins do not lock the account
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

def test_lockout_after_five_failures_even_with_right_password():
    with client() as cl:
        name, _ = new_user(cl)
        for _ in range(5):
            assert cl.post("/auth/login", json={"username": name, "password": "wrongpass1"}).status_code == 401
        assert cl.post("/auth/login", json={"username": name, "password": "password123"}).status_code == 429


def test_four_failures_do_not_lock():
    with client() as cl:
        name, _ = new_user(cl)
        for _ in range(4):
            cl.post("/auth/login", json={"username": name, "password": "wrongpass1"})
        assert cl.post("/auth/login", json={"username": name, "password": "password123"}).status_code == 200
