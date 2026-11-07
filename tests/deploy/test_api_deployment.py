"""Builds and runs the API image the way it is deployed, then probes it over real HTTP."""
import shutil
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.docker


def docker_up():
    return shutil.which("docker") and subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@pytest.fixture(scope="module")
def deployed():
    if not docker_up():
        pytest.skip("docker unavailable")
    subprocess.run(["docker", "build", "-q", "-f", "deploy/Dockerfile", "-t", "sharley-api:test", "."], cwd=ROOT,
                   check=True, capture_output=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    cid = subprocess.run(["docker", "run", "-d", "--rm", "-p", f"127.0.0.1:{port}:8000", "-e",
                          "SHARLEY_CORS_ORIGINS=https://sharley.pages.dev", "sharley-api:test"],
                         check=True, capture_output=True, text=True).stdout.strip()
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            if httpx.get(base + "/api/health", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.5)
    else:
        logs = subprocess.run(["docker", "logs", cid], capture_output=True, text=True).stderr[-800:]
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True)
        pytest.fail("API container did not become healthy:\n" + logs)
    yield base, cid
    subprocess.run(["docker", "rm", "-f", cid], capture_output=True)


def test_health_runs_offline_with_json_store(deployed):
    base, _ = deployed
    h = httpx.get(base + "/api/health").json()
    assert h["status"] == "ok" and h["offline"] is True


def test_demo_fixture_is_served_and_has_the_headline_story(deployed):
    base, _ = deployed
    demo = httpx.get(base + "/api/demo").json()
    assert demo["events"][-1]["verdict"]["status"] == "Wrong Answer"
    assert {v["decision"] for v in demo["timeline"]} >= {"adopted", "rolled_back"}


def test_cors_only_for_the_configured_origin(deployed):
    base, _ = deployed
    ok = httpx.get(base + "/api/health", headers={"Origin": "https://sharley.pages.dev"})
    bad = httpx.get(base + "/api/health", headers={"Origin": "https://evil.example"})
    assert ok.headers["access-control-allow-origin"] == "https://sharley.pages.dev"
    assert "access-control-allow-origin" not in bad.headers


def test_errors_are_json_without_stack_traces(deployed):
    base, _ = deployed
    for r in (httpx.get(base + "/api/banks/nope:0"), httpx.post(base + "/api/specs", json={"text": ""}),
              httpx.post(base + "/api/specs", content=b"{broken", headers={"content-type": "application/json"})):
        assert r.status_code in (404, 422) and "Traceback" not in r.text


def test_container_runs_unprivileged_with_no_secrets_baked_in(deployed):
    _, cid = deployed
    who = subprocess.run(["docker", "exec", cid, "id", "-u"], capture_output=True, text=True).stdout.strip()
    assert who != "0"
    found = subprocess.run(["docker", "exec", cid, "sh", "-c", "ls -a /srv | grep -E '^\\.env' || true"],
                           capture_output=True, text=True).stdout
    assert found.strip() == ""
