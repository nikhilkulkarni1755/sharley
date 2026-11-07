# reqs: R10
# hint: error responses expose internal details
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

def test_server_errors_do_not_leak_tracebacks():
    with client() as cl:
        _, auth = new_user(cl)
        r = cl.get("/notes/99999999999999999999", headers=auth)
        assert "Traceback" not in r.text and 'File "' not in r.text and "sqlite" not in r.text.lower()
        assert r.status_code in (404, 422, 500)
