# reqs: R6
# hint: listing, searching or paging notes is wrong
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

def test_list_returns_only_own_notes_in_order():
    with client() as cl:
        _, auth = new_user(cl)
        ids = [add_note(cl, auth, title=f"note{i}") for i in range(3)]
        assert [n["id"] for n in cl.get("/notes", headers=auth).json()] == ids


def test_search_by_title():
    with client() as cl:
        _, auth = new_user(cl)
        add_note(cl, auth, title="groceries")
        add_note(cl, auth, title="work")
        assert [n["title"] for n in cl.get("/notes", params={"q": "groc"}, headers=auth).json()] == ["groceries"]


def test_paging_defaults_and_limits():
    with client() as cl:
        _, auth = new_user(cl)
        for i in range(25):
            add_note(cl, auth, title=f"n{i}")
        assert len(cl.get("/notes", headers=auth).json()) == 20
        assert len(cl.get("/notes", params={"limit": 100}, headers=auth).json()) == 25
        assert cl.get("/notes", params={"limit": 101}, headers=auth).status_code == 422
        assert cl.get("/notes", params={"limit": 0}, headers=auth).status_code == 422
        assert cl.get("/notes", params={"offset": -1}, headers=auth).status_code == 422
        assert len(cl.get("/notes", params={"limit": 10, "offset": 20}, headers=auth).json()) == 5
        assert len(cl.get("/notes", params={"limit": 1}, headers=auth).json()) == 1
