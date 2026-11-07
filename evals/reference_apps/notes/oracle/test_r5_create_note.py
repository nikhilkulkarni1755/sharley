# reqs: R5
# hint: notes can be created with invalid sizes or are returned wrongly
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

def test_create_note_shape_and_status():
    with client() as cl:
        _, auth = new_user(cl)
        r = cl.post("/notes", json={"title": "Hello", "body": "World"}, headers=auth)
        assert r.status_code == 201 and r.json()["title"] == "Hello" and r.json()["body"] == "World" and "id" in r.json()


def test_title_and_body_boundaries():
    with client() as cl:
        _, auth = new_user(cl)
        assert cl.post("/notes", json={"title": "x" * 100, "body": ""}, headers=auth).status_code == 201
        assert cl.post("/notes", json={"title": "x" * 101, "body": ""}, headers=auth).status_code == 422
        assert cl.post("/notes", json={"title": "", "body": ""}, headers=auth).status_code == 422
        assert cl.post("/notes", json={"title": "  ", "body": ""}, headers=auth).status_code == 422
        assert cl.post("/notes", json={"title": "t", "body": "y" * 10000}, headers=auth).status_code == 201
        assert cl.post("/notes", json={"title": "t", "body": "y" * 10001}, headers=auth).status_code == 422
