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


# ---- image intake
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


def test_image_intake_produces_a_spec(tmp_path):
    import base64
    desc = json.dumps({"entities": ["User", "Note"], "flows": ["login then list notes"]})
    extract = json.dumps({"requirements": [{"text": "User can log in", "category": "functional",
                                            "source_span": "Flow: login then list notes"}]})
    replies = iter([desc, extract, '{"mappings": []}'])
    from sharley.harness.provider import ModelProvider

    class Seq(ModelProvider):
        name, model, family = "seq", "seq", "fake"
        health = lambda self: True  # noqa: E731
        complete = lambda self, system, user, *, images=None: next(replies)  # noqa: E731

    ctx = Context(env={}, repo=JsonRepository(tmp_path), verifier=FallbackChain([Seq()]),
                  long_context=FallbackChain([ScriptedProvider("s")]), sandbox=FakeSandbox())
    r = TestClient(create_app(ctx)).post("/api/specs/image", json={"image_b64": base64.b64encode(PNG).decode()})
    assert r.status_code == 200 and r.json()["requirements"][0]["evidence"]["kind"] == "observed"


@pytest.mark.parametrize("payload", ["not base64!!", "R0lGODlhAQABAAAAACw=", ""])
def test_image_intake_rejects_bad_payloads(client, payload):
    import base64
    body = {"image_b64": payload}
    assert client.post("/api/specs/image", json=body).status_code == 422
    assert client.post("/api/specs/image", json={"image_b64": base64.b64encode(b"<svg onload=1>").decode()}).status_code == 422


def test_samples_endpoint_serves_spec_and_clean_source_but_no_sealed_content(tmp_path):
    from evals.sample_backends import register
    from sharley.judge import save_bank, split_bank
    from tests.gate.test_gate import FakeSandbox as FS
    ctx = Context(env={"SHARLEY_HOME": str(tmp_path)}, repo=JsonRepository(tmp_path / "db"), verifier=FallbackChain([EchoWriter(EXTRACT)]),
                  long_context=FallbackChain([ScriptedProvider("s")]), sandbox=FS())
    c = TestClient(create_app(ctx))
    before = c.get("/api/samples").json()
    assert [s["name"] for s in before] == ["payments", "electricity"] and all(s["bank"] is None for s in before)
    spec = c.post("/api/specs", json={"text": "Users create notes and never read other notes."}).json()
    bank = c.post("/api/banks", json={"spec_hash": spec["spec_hash"]}).json()
    register(tmp_path, "payments", bank["key"])
    after = {s["name"]: s for s in c.get("/api/samples").json()}
    assert after["payments"]["bank"]["key"] == bank["key"] and after["electricity"]["bank"] is None
    blob = json.dumps(after)
    assert "FLAW" not in blob and "flaws.json" not in blob and "FLAWS.md" not in blob
    assert all(t["locked"] for t in after["payments"]["bank"]["sealed"])


# ---- public-mode guard
def public_client(tmp_path, **guard_kw):
    from sharley.api.guard import Guard
    ctx = Context(env={}, repo=JsonRepository(tmp_path / "db"), verifier=FallbackChain([EchoWriter(EXTRACT)]),
                  long_context=FallbackChain([ScriptedProvider("s")]), sandbox=FakeSandbox())
    return TestClient(create_app(ctx, guard=Guard(public=True, admin_key="s3cret", **guard_kw))), ctx


def test_paid_endpoints_need_the_admin_key_in_public_mode_but_free_ones_do_not(tmp_path):
    c, _ = public_client(tmp_path)
    for path, body in (("/api/specs", {"text": "x" * 20}), ("/api/banks", {"spec_hash": "h"}), ("/api/chat", {"session": "s", "text": "hello there friend"}),
                       ("/api/specs/image", {"image_b64": "AAAA"})):
        assert c.post(path, json=body).status_code == 403
        assert c.post(path, json=body, headers={"x-sharley-key": "wrong"}).status_code == 403
    assert c.get("/api/health").status_code == 200 and c.get("/api/samples").status_code == 200
    assert c.post("/api/specs", json={"text": "Users create notes."}, headers={"x-sharley-key": "s3cret"}).status_code == 200


def test_public_mode_without_a_configured_key_locks_paid_endpoints_completely(tmp_path):
    from sharley.api.guard import Guard
    ctx = Context(env={}, repo=JsonRepository(tmp_path), verifier=FallbackChain([ScriptedProvider("a")]),
                  long_context=FallbackChain([ScriptedProvider("s")]), sandbox=FakeSandbox())
    c = TestClient(create_app(ctx, guard=Guard(public=True, admin_key="")))
    assert c.post("/api/specs", json={"text": "hello world spec"}, headers={"x-sharley-key": ""}).status_code == 403


def test_guard_reads_environment():
    from sharley.api.guard import Guard
    g = Guard.from_env({"SHARLEY_PUBLIC_MODE": "1", "SHARLEY_ADMIN_KEY": "k", "SHARLEY_RUNS_PER_MINUTE": "2", "SHARLEY_MAX_CONCURRENT_RUNS": "1"})
    assert (g.public, g.admin_key, g.runs_per_minute, g.max_concurrent) == (True, "k", 2, 1)
    assert Guard.from_env({}).public is False


def _bank(c, ctx):
    spec = TestClient(create_app(ctx)).post("/api/specs", json={"text": "Users create notes and never read other notes."}).json()
    return TestClient(create_app(ctx)).post("/api/banks", json={"spec_hash": spec["spec_hash"]}).json()


def run_body(bank):
    return {"bank": bank["key"], "implementer_model": "m", "implementer_family": "google", "files": {"app/x.py": "x"}}


def test_runs_are_rate_limited_per_ip_and_cap_resets_when_runs_finish(tmp_path):
    c, ctx = public_client(tmp_path, runs_per_minute=2, max_concurrent=5)
    bank = _bank(c, ctx)
    ok = [c.post("/api/runs", json=run_body(bank), headers={"cf-connecting-ip": "1.2.3.4"}) for _ in range(3)]
    assert [r.status_code for r in ok] == [202, 202, 429] and "wait a minute" in ok[2].json()["detail"]
    assert c.post("/api/runs", json=run_body(bank), headers={"cf-connecting-ip": "5.6.7.8"}).status_code == 202  # other address unaffected


def test_concurrency_cap_blocks_then_releases(tmp_path):
    import time as _t
    from sharley.api.guard import Guard
    g = Guard(public=True, admin_key="k", runs_per_minute=100, max_concurrent=1)
    ctx = Context(env={}, repo=JsonRepository(tmp_path / "db"), verifier=FallbackChain([EchoWriter(EXTRACT)]),
                  long_context=FallbackChain([ScriptedProvider("s")]), sandbox=FakeSandbox())
    c = TestClient(create_app(ctx, guard=g))
    bank = _bank(c, ctx)

    class Req:
        headers = {}
        client = None
    g.acquire_run(Req())  # one run "in flight"
    busy = c.post("/api/runs", json=run_body(bank))
    assert busy.status_code == 429 and "busy" in busy.json()["detail"]
    g.release_run()
    assert c.post("/api/runs", json=run_body(bank)).status_code == 202
    for _ in range(100):  # the finished background run must release its own slot
        if g._active == 0:
            break
        _t.sleep(0.05)
    assert g._active == 0


def test_finished_runs_delete_their_workspace(tmp_path):
    import glob, tempfile, time as _t
    before = set(glob.glob(tempfile.gettempdir() + "/sharley-sub-*"))
    c, ctx = public_client(tmp_path)
    bank = _bank(c, ctx)
    run = c.post("/api/runs", json=run_body(bank)).json()
    wait_events(c, run["run_id"])
    _t.sleep(0.3)
    assert set(glob.glob(tempfile.gettempdir() + "/sharley-sub-*")) == before
