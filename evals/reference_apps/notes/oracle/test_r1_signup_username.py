# reqs: R1
# hint: signup accepts or rejects usernames incorrectly
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

def test_valid_signup_returns_201_and_no_password():
    with client() as cl:
        r = cl.post("/auth/signup", json={"username": "a" + uuid.uuid4().hex[:8], "password": "password123"})
        assert r.status_code == 201 and "password" not in r.text and "pw_hash" not in r.text


def test_username_length_boundaries():
    with client() as cl:
        ok3 = "a" + uuid.uuid4().hex[:2]
        ok32 = "b" * 22 + uuid.uuid4().hex[:10]
        assert cl.post("/auth/signup", json={"username": ok3, "password": "password123"}).status_code == 201
        assert cl.post("/auth/signup", json={"username": ok32, "password": "password123"}).status_code == 201
        assert cl.post("/auth/signup", json={"username": "ab", "password": "password123"}).status_code == 422
        assert cl.post("/auth/signup", json={"username": "c" * 33, "password": "password123"}).status_code == 422


def test_username_charset_and_duplicates():
    with client() as cl:
        assert cl.post("/auth/signup", json={"username": "bad name!", "password": "password123"}).status_code == 422
        name = "d" + uuid.uuid4().hex[:8]
        assert cl.post("/auth/signup", json={"username": name, "password": "password123"}).status_code == 201
        assert cl.post("/auth/signup", json={"username": name, "password": "password123"}).status_code == 409
