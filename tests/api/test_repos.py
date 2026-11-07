import glob
import json
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agents.repo import BadRepo, validate
from evals.sample_backends import SAMPLE_REPOS, register, sample_for_url
from sharley.api import create_app
from sharley.api.guard import Guard
from sharley.gate.context import Context
from sharley.gate.service import make_bank
from sharley.harness import FallbackChain
from sharley.runner.base import RunReport, Sandbox, TestResult
from sharley.storage import JsonRepository
from tests.fakes import EchoWriter, ScriptedProvider
from tests.gate.test_gate import EXTRACT, FakeSandbox, spec_obj

PAYMENTS = SAMPLE_REPOS["payments"]


def fake_fetch(files=None):
    def fetch(url, branch):
        validate(url, branch)
        d = Path(tempfile.mkdtemp(prefix="sharley-repo-test-")) / "src"
        (d / "app").mkdir(parents=True)
        for rel, text in (files or {"app/main.py": '@app.get("/health")\ndef health(): return {"ok": True}\n'}).items():
            (d / rel).write_text(text)
        return d
    return fetch


def make(tmp_path, sandbox=None, guard=None, fetch=None, prepared=True):
    chain = FallbackChain([EchoWriter(EXTRACT)])
    ctx = Context(env={"SHARLEY_HOME": str(tmp_path)}, repo=JsonRepository(tmp_path / "db"), verifier=chain,
                  long_context=FallbackChain([ScriptedProvider("s")]), sandbox=sandbox or FakeSandbox())
    if prepared:
        bank = make_bank(spec_obj(), ctx.repo, chain)
        register(tmp_path, "payments", f"{bank.spec_hash}:{bank.seed}")
    return TestClient(create_app(ctx, guard=guard, fetch=fetch or fake_fetch())), ctx


def events(c, run_id):
    with c.stream("GET", f"/api/runs/{run_id}/events") as r:
        text = "".join(r.iter_text())
    return [json.loads(l[6:]) for l in text.splitlines() if l.startswith("data: ")]


def test_known_sample_repo_is_judged_against_its_prebuilt_hidden_tests_for_free(tmp_path):
    c, ctx = make(tmp_path)
    r = c.post("/api/repos", json={"url": PAYMENTS})
    assert r.status_code == 202 and r.json()["mode"] == "sealed"
    ev = events(c, r.json()["run_id"])
    kinds = [e["type"] for e in ev]
    assert kinds[:2] == ["stage", "surface"] and kinds[-1] == "verdict" and "sealed" in kinds and "example" in kinds
    assert ev[-1]["verdict"]["status"] == "Accepted"
    assert all(set(e) == {"type", "index", "passed"} for e in ev if e["type"] == "sealed")  # tiles only, never test content


def test_sample_url_matching_is_exact_not_a_prefix_or_lookalike():
    assert sample_for_url(PAYMENTS + ".git/") == "payments" and sample_for_url(PAYMENTS.upper().replace("HTTPS", "https")) == "payments"
    for u in (PAYMENTS + "-evil", PAYMENTS.replace("nikhilkulkarni1755", "someone-else"), "https://github.com/a/b"):
        assert sample_for_url(u) is None


def test_unprepared_sample_is_a_clean_503(tmp_path):
    c, _ = make(tmp_path, prepared=False)
    r = c.post("/api/repos", json={"url": PAYMENTS})
    assert r.status_code == 503 and "not prepared" in r.json()["detail"]


def test_any_other_repo_is_audited_with_generated_tests_and_findings_are_streamed(tmp_path):
    class OneFails(Sandbox):
        name = "one-fails"
        health = lambda self: True  # noqa: E731

        def run(self, workspace, tests, stack, *, timeout_s=180):
            return RunReport(results=[TestResult(test_id=t.id, passed=i != 0, kind="pass" if i else "assert", output="expected 403, got 200")
                                      for i, t in enumerate(tests)])

    c, _ = make(tmp_path, sandbox=OneFails(), prepared=False)
    r = c.post("/api/repos", json={"url": "https://github.com/acme/widgets", "branch": "main"})
    assert r.status_code == 202 and r.json()["mode"] == "audit"
    ev = events(c, r.json()["run_id"])
    kinds = [e["type"] for e in ev]
    assert kinds[0] == "stage" and "surface" in kinds and kinds.count("finding") == 1 and kinds[-1] == "report"
    stages = [e["stage"] for e in ev if e["type"] == "stage"]
    assert stages == ["cloning", "analyzing", "writing_tests", "running_tests"]
    finding = next(e for e in ev if e["type"] == "finding")
    assert finding["requirement_ids"] and finding["requirement_text"] and "expected 403" in finding["message"]
    rep = ev[-1]
    assert rep["failed"] == 1 and rep["total"] == rep["passed"] + 1 and rep["boot_ok"] is True


def test_audit_reports_a_repo_that_cannot_boot_instead_of_pretending(tmp_path):
    c, _ = make(tmp_path, sandbox=FakeSandbox(boot_ok=False, build_output="ModuleNotFoundError: No module named 'django'"), prepared=False)
    rid = c.post("/api/repos", json={"url": "https://github.com/acme/django-app"}).json()["run_id"]
    rep = events(c, rid)[-1]
    assert rep["type"] == "report" and rep["boot_ok"] is False and "django" in rep["build_output"] and rep["passed"] == 0


# ---- misuse
@pytest.mark.parametrize("url", ["file:///etc/passwd", "ext::sh -c evil", "https://evil.com/a/b", "http://github.com/a/b",
                                 "https://github.com/a/b; rm -rf /", "-u https://github.com/a/b", "git@github.com:a/b.git", ""])
def test_hostile_urls_are_rejected_before_any_clone(tmp_path, url):
    calls = []
    c, _ = make(tmp_path, fetch=lambda u, b: calls.append(u), prepared=False)
    assert c.post("/api/repos", json={"url": url}).status_code == 422 and calls == []


def test_hostile_branch_is_rejected(tmp_path):
    c, _ = make(tmp_path, prepared=False)
    assert c.post("/api/repos", json={"url": "https://github.com/a/b", "branch": "--upload-pack=x"}).status_code == 422


def test_public_deployment_lets_anyone_judge_samples_but_audits_need_the_admin_key(tmp_path):
    c, _ = make(tmp_path, guard=Guard(public=True, admin_key="s3cret"))
    assert c.post("/api/repos", json={"url": PAYMENTS}).status_code == 202
    other = {"url": "https://github.com/acme/widgets"}
    assert c.post("/api/repos", json=other).status_code == 403
    assert c.post("/api/repos", json=other, headers={"x-sharley-key": "wrong"}).status_code == 403
    assert c.post("/api/repos", json=other, headers={"x-sharley-key": "s3cret"}).status_code == 202


def test_repo_runs_share_the_rate_limit_and_release_their_slot(tmp_path):
    g = Guard(public=False, runs_per_minute=1, max_concurrent=5)
    c, _ = make(tmp_path, guard=g)
    first = c.post("/api/repos", json={"url": PAYMENTS})
    assert first.status_code == 202 and c.post("/api/repos", json={"url": PAYMENTS}).status_code == 429
    events(c, first.json()["run_id"])
    for _ in range(100):
        if g._active == 0:
            break
        time.sleep(0.05)
    assert g._active == 0


def test_clone_failure_becomes_an_error_event_and_leaves_no_temp_dirs(tmp_path):
    before = set(glob.glob(tempfile.gettempdir() + "/sharley-repo-test-*"))

    def boom(url, branch):
        raise BadRepo("could not clone that repository (is it public, and does the branch exist?)")

    c, _ = make(tmp_path, fetch=boom, prepared=False)
    ev = events(c, c.post("/api/repos", json={"url": "https://github.com/a/missing"}).json()["run_id"])
    assert ev[-1]["type"] == "error" and "could not clone" in ev[-1]["detail"]
    c2, _ = make(tmp_path / "ok")
    events(c2, c2.post("/api/repos", json={"url": PAYMENTS}).json()["run_id"])
    time.sleep(0.3)
    assert set(glob.glob(tempfile.gettempdir() + "/sharley-repo-test-*")) == before


def test_samples_listing_for_the_quick_pick_buttons(tmp_path):
    c, _ = make(tmp_path, prepared=False)
    s = c.get("/api/repos/samples").json()
    assert [x["name"] for x in s] == ["payments", "electricity"] and all(x["url"].startswith("https://github.com/") and x["pitch"] for x in s)
