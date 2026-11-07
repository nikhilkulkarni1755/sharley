import json
import time

import pytest
from fastapi.testclient import TestClient

from sharley.api import create_app
from sharley.gate.context import Context
from sharley.harness import FallbackChain
from sharley.storage import JsonRepository
from tests.fakes import EchoWriter, ScriptedProvider
from tests.gate.test_gate import FakeSandbox

EXTRACT = json.dumps({"requirements": [
    {"text": "Users can create notes", "category": "functional", "source_span": "create notes"},
    {"text": "Users cannot read other notes", "category": "security", "source_span": "never read other notes"},
    {"text": "App serves a health check", "category": "deployment", "assumption": "deploy norm"}]})


@pytest.fixture
def client(tmp_path):
    chain = FallbackChain([EchoWriter(EXTRACT)])
    ctx = Context(env={}, repo=JsonRepository(tmp_path / "db"), verifier=chain,
                  long_context=FallbackChain([ScriptedProvider("s")]), sandbox=FakeSandbox())
    c = TestClient(create_app(ctx))
    c.ctx = ctx
    return c


def make_bank(client):
    spec = client.post("/api/specs", json={"text": "Users create notes and never read other notes."}).json()
    return client.post("/api/banks", json={"spec_hash": spec["spec_hash"], "stack": "docker-api"}).json(), spec


def wait_events(client, run_id):
    with client.stream("GET", f"/api/runs/{run_id}/events") as r:
        text = "".join(r.iter_text())
    return [json.loads(l[6:]) for l in text.splitlines() if l.startswith("data: ")]


# ---- happy path
def test_health_reports_providers_and_sandbox(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["sandbox"] == "fake" and "providers" in h


def test_spec_to_bank_to_streamed_verdict(client):
    bank, spec = make_bank(client)
    assert spec["requirements"][0]["id"] == "R1" and spec["coverage_pct"] >= 0
    assert bank["examples"] and bank["sealed"] and all(t["locked"] for t in bank["sealed"])
    r = client.post("/api/runs", json={"bank": bank["key"], "implementer_model": "argon", "implementer_family": "google",
                                       "files": {"app/main.py": "print(1)"}})
    assert r.status_code == 202
    events = wait_events(client, r.json()["run_id"])
    kinds = [e["type"] for e in events]
    assert kinds.count("example") == len(bank["examples"]) and kinds.count("sealed") == len(bank["sealed"])
    assert kinds[-1] == "verdict" and events[-1]["verdict"]["status"] == "Accepted"
    assert [e["index"] for e in events if e["type"] == "sealed"] == list(range(1, len(bank["sealed"]) + 1))


def test_get_bank_roundtrip_and_timeline_empty(client):
    bank, _ = make_bank(client)
    assert client.get(f"/api/banks/{bank['key']}").json() == bank
    assert client.get("/api/skills/timeline").json() == []


# ---- the invariant: sealed content never leaves the server
class UniqueWriter(EchoWriter):
    """Every written test carries unique code, name and hint so leaks are detectable by substring."""

    def complete(self, system, user, *, images=None):
        import re
        if "QA engineer" in system or "security tester" in system:
            ids = sorted(set(re.findall(r'"id":"(R\d+)"', user)))
            return json.dumps({"tests": [{"name": f"name-{i}-{n}", "code": f"def test_{i.lower()}_{n}():\n    assert 1  # CODE-{i}-{n}\n",
                                          "requirement_ids": [i], "hint": f"hint about {i} {n}"} for n in range(3) for i in ids]})
        return super().complete(system, user, images=images)


def test_no_response_ever_contains_sealed_code_names_or_hints(tmp_path):
    reqs = [{"text": f"Requirement {i}", "category": "functional" if i < 5 else "security", "assumption": "norm"} for i in range(1, 7)]
    chain = FallbackChain([UniqueWriter(json.dumps({"requirements": reqs}))])
    ctx = Context(env={}, repo=JsonRepository(tmp_path / "db"), verifier=chain,
                  long_context=FallbackChain([ScriptedProvider("s")]), sandbox=FakeSandbox())
    client = TestClient(create_app(ctx))
    spec = client.post("/api/specs", json={"text": "six things"}).json()
    bank = client.post("/api/banks", json={"spec_hash": spec["spec_hash"]}).json()
    from sharley.judge import load_bank
    real = load_bank(ctx.repo, bank["key"])
    run = client.post("/api/runs", json={"bank": bank["key"], "implementer_model": "m", "implementer_family": "google",
                                         "files": {}}).json()
    seen = json.dumps(bank) + json.dumps(wait_events(client, run["run_id"])) + json.dumps(client.get(f"/api/banks/{bank['key']}").json())
    assert real.sealed and real.examples
    for t in real.sealed:
        for secret in (t.code.split("# ")[1].strip(), t.name, t.hint, t.file):
            assert secret not in seen, f"sealed {t.id} leaked {secret!r}"
    assert any(t.name in seen for t in real.examples)  # sanity: examples ARE shown
    assert set(bank["sealed"][0]) == {"index", "family", "locked"}


# ---- misuse
def test_unknown_resources_404(client):
    assert client.get("/api/banks/nope:0").status_code == 404
    assert client.get("/api/runs/nope/events").status_code == 404
    assert client.post("/api/banks", json={"spec_hash": "nope"}).status_code == 404
    assert client.post("/api/runs", json={"bank": "nope:0", "implementer_model": "m", "implementer_family": "g", "files": {}}).status_code == 404


@pytest.mark.parametrize("body", [{}, {"text": ""}, {"text": "x" * 200_001}, {"text": 5}])
def test_spec_request_validation(client, body):
    assert client.post("/api/specs", json=body).status_code == 422


def test_unsupported_stack_and_same_family_rejected(client):
    bank, spec = make_bank(client)
    assert client.post("/api/banks", json={"spec_hash": spec["spec_hash"], "stack": "rails"}).status_code == 422
    r = client.post("/api/runs", json={"bank": bank["key"], "implementer_model": "m", "implementer_family": "fake", "files": {}})
    assert r.status_code == 422 and "different model families" in r.json()["detail"]


def test_hostile_submission_paths_are_rejected_not_written(client, tmp_path):
    bank, _ = make_bank(client)
    files = {"../../evil.py": "x", "/etc/passwd": "x", "tests/test_1.py": "def test_x(): pass", ".env": "K=1", "app/ok.py": "ok"}
    r = client.post("/api/runs", json={"bank": bank["key"], "implementer_model": "m", "implementer_family": "google", "files": files})
    assert r.status_code == 202
    assert set(r.json()["rejected_paths"]) == {"../../evil.py", "/etc/passwd", "tests/test_1.py", ".env"}
    last = wait_events(client, r.json()["run_id"])[-1]
    assert last["type"] == "verdict" and last["verdict"]["status"] != "Rejected: tests tampered"


def test_oversized_file_rejected_with_413(client):
    bank, _ = make_bank(client)
    r = client.post("/api/runs", json={"bank": bank["key"], "implementer_model": "m", "implementer_family": "google",
                                       "files": {"a.py": "x" * 100_001}})
    assert r.status_code == 413


def test_provider_outage_is_a_clean_503_without_stack_trace(tmp_path):
    ctx = Context(env={}, repo=JsonRepository(tmp_path), verifier=FallbackChain([ScriptedProvider("dead")]),
                  long_context=FallbackChain([ScriptedProvider("s")]), sandbox=FakeSandbox())
    r = TestClient(create_app(ctx)).post("/api/specs", json={"text": "build a thing"})
    assert r.status_code == 503 and "retry" in r.json()["detail"] and "Traceback" not in r.text


def test_cors_allows_only_configured_origin(tmp_path):
    ctx = Context(env={}, repo=JsonRepository(tmp_path), verifier=FallbackChain([ScriptedProvider("a")]),
                  long_context=FallbackChain([ScriptedProvider("s")]), sandbox=FakeSandbox())
    c = TestClient(create_app(ctx, ["https://sharley.pages.dev"]))
    ok = c.get("/api/health", headers={"Origin": "https://sharley.pages.dev"})
    bad = c.get("/api/health", headers={"Origin": "https://evil.example"})
    assert ok.headers.get("access-control-allow-origin") == "https://sharley.pages.dev"
    assert "access-control-allow-origin" not in bad.headers


def test_demo_fixture_404_until_built(client, monkeypatch, tmp_path):
    import sharley.api.app as mod
    monkeypatch.setattr(mod, "DEMO_FIXTURE", tmp_path / "missing.json")
    assert client.get("/api/demo").status_code == 404
    (tmp_path / "demo.json").write_text('{"ok": true}')
    monkeypatch.setattr(mod, "DEMO_FIXTURE", tmp_path / "demo.json")
    assert client.get("/api/demo").json() == {"ok": True}
