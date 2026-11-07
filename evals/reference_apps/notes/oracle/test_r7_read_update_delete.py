# reqs: R7
# hint: reading, editing or deleting a note by id is wrong
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

def test_read_update_delete_roundtrip():
    with client() as cl:
        _, auth = new_user(cl)
        nid = add_note(cl, auth, title="a", body="b")
        assert cl.get(f"/notes/{nid}", headers=auth).json() == {"id": nid, "title": "a", "body": "b"}
        up = cl.put(f"/notes/{nid}", json={"title": "a2", "body": "b2"}, headers=auth)
        assert up.status_code == 200 and up.json()["title"] == "a2"
        assert cl.get(f"/notes/{nid}", headers=auth).json()["body"] == "b2"
        assert cl.delete(f"/notes/{nid}", headers=auth).status_code == 204
        assert cl.get(f"/notes/{nid}", headers=auth).status_code == 404


def test_update_validates_input_and_missing_note_is_404():
    with client() as cl:
        _, auth = new_user(cl)
        nid = add_note(cl, auth)
        assert cl.put(f"/notes/{nid}", json={"title": "", "body": ""}, headers=auth).status_code == 422
        assert cl.put("/notes/999999999", json={"title": "t", "body": ""}, headers=auth).status_code == 404
        assert cl.delete("/notes/999999999", headers=auth).status_code == 404
