# reqs: R8
# hint: users can read each other's notes
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

def test_cannot_read_update_or_delete_another_users_note():
    with client() as cl:
        _, alice = new_user(cl)
        _, bob = new_user(cl)
        nid = add_note(cl, alice, title="private", body="secret")
        assert cl.get(f"/notes/{nid}", headers=bob).status_code == 404
        assert cl.put(f"/notes/{nid}", json={"title": "pwn", "body": ""}, headers=bob).status_code == 404
        assert cl.delete(f"/notes/{nid}", headers=bob).status_code == 404
        assert cl.get(f"/notes/{nid}", headers=alice).json()["title"] == "private"


def test_lists_never_include_other_users_notes():
    with client() as cl:
        _, alice = new_user(cl)
        _, bob = new_user(cl)
        add_note(cl, alice, title="alice-only")
        assert cl.get("/notes", headers=bob).json() == []
        assert cl.get("/notes", params={"q": "alice"}, headers=bob).json() == []
