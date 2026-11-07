# reqs: R11
# hint: user input can alter database queries
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

def test_search_term_cannot_break_out_of_query():
    with client() as cl:
        _, alice = new_user(cl)
        _, bob = new_user(cl)
        add_note(cl, alice, title="alice-secret")
        r = cl.get("/notes", params={"q": "' OR '1'='1"}, headers=bob)
        assert r.status_code == 200 and r.json() == []


def test_note_id_injection_is_rejected():
    with client() as cl:
        _, alice = new_user(cl)
        _, bob = new_user(cl)
        nid = add_note(cl, alice)
        r = cl.get(f"/notes/{nid}%20OR%201=1", headers=bob)
        assert r.status_code in (404, 422)
        assert "alice" not in r.text


def test_login_injection_does_not_authenticate():
    with client() as cl:
        r = cl.post("/auth/login", json={"username": "admin' --", "password": "x"})
        assert r.status_code == 401
