# reqs: R9
# hint: some endpoints work without a valid token
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

def test_protected_routes_reject_missing_or_bad_tokens():
    with client() as cl:
        _, auth = new_user(cl)
        nid = add_note(cl, auth)
        for bad in ({}, {"Authorization": "Bearer nope"}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer x"}):
            assert cl.get("/notes", headers=bad).status_code == 401
            assert cl.post("/notes", json={"title": "t", "body": ""}, headers=bad).status_code == 401
            assert cl.get(f"/notes/{nid}", headers=bad).status_code == 401
            assert cl.put(f"/notes/{nid}", json={"title": "t", "body": ""}, headers=bad).status_code == 401
            assert cl.delete(f"/notes/{nid}", headers=bad).status_code == 401


def test_public_routes_need_no_token():
    with client() as cl:
        assert cl.get("/health").status_code == 200
