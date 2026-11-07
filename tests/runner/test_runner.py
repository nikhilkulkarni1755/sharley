import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from sharley.runner import DockerSandbox
from sharley.runner.docker import ExecResult, docker_argv, run_script, subprocess_exec
from sharley.runner.parse import parse_pytest, parse_vitest
from sharley.schemas import TestCase


def tc(i, file=None, code="def test_x():\n    assert True\n"):
    return TestCase(id=f"T{i}", requirement_ids=["R1"], name="n", family="functional",
                    file=file or f"tests/test_{i}.py", code=code)


SUMMARY = """noise
=========================== short test summary info ============================
PASSED tests/test_1.py::test_a
PASSED tests/test_1.py::test_b
FAILED tests/test_2.py::test_a - AssertionError: assert 403 == 200
ERROR tests/test_3.py::test_a - httpx.ConnectError: refused
PASSED tests/test_4.py::test_a
FAILED tests/test_4.py::test_b - assert 1 == 2
"""


# ---- parsing
def test_pytest_summary_maps_files_to_cases():
    r = {x.test_id: x for x in parse_pytest(SUMMARY, [tc(1), tc(2), tc(3), tc(4), tc(5)])}
    assert r["T1"].passed and r["T1"].kind == "pass"
    assert r["T2"].kind == "assert" and "403" in r["T2"].output
    assert r["T3"].kind == "runtime"
    assert r["T4"].kind == "assert" and not r["T4"].passed  # one failing test fails the case
    assert r["T5"].kind == "runtime" and "not collected" in r["T5"].output


def test_forged_pass_lines_before_summary_are_ignored():
    forged = "PASSED tests/test_1.py::test_a\n" + "short test summary info\nFAILED tests/test_1.py::test_a - AssertionError\n"
    assert parse_pytest(forged, [tc(1)])[0].passed is False
    assert parse_pytest("PASSED tests/test_1.py::test_a\n", [tc(1)])[0].passed is False  # no summary at all


def test_vitest_json_parsing():
    data = {"numTotalTestSuites": 2, "testResults": [
        {"name": "/app/tests/a.test.ts", "status": "passed", "assertionResults": []},
        {"name": "/app/tests/b.test.ts", "status": "failed",
         "assertionResults": [{"failureMessages": ["AssertionError: expected 403 to be 200"]}]}]}
    out = "log line\n" + json.dumps(data)
    a, b, c = (tc(i, file=f"tests/{n}.test.ts", code="test('a',()=>{})") for i, n in ((1, "a"), (2, "b"), (3, "c")))
    r = {x.test_id: x for x in parse_vitest(out, [a, b, c])}
    assert r["T1"].passed and r["T2"].kind == "assert" and r["T3"].kind == "runtime"
    assert parse_vitest("garbage", [a])[0].kind == "runtime"


# ---- isolation flags
def test_docker_argv_is_locked_down():
    argv = docker_argv("n", "img", Path("/s"))
    s = " ".join(argv)
    for needle in ("--network none", "--read-only", "--cap-drop ALL", "no-new-privileges", "--pids-limit",
                   "--memory", "-u 65534:65534", "/work:ro", "/tests:ro", "/harness:ro"):
        assert needle in s
    assert "docker.sock" not in s and "--privileged" not in s and "-v /:" not in s


def test_run_script_lists_only_requested_test_files():
    s = run_script("docker-api", ["tests/test_1.py"])
    assert "pytest" in s and "tests/test_1.py" in s and "127.0.0.1:8000/health" in s and "uvicorn" in s


# ---- run() with a fake executor
class Recorder:
    def __init__(self, result=None):
        self.calls, self.snapshot, self.result = [], {}, result or ExecResult(0, SUMMARY)

    def __call__(self, argv, timeout):
        self.calls.append(argv)
        if argv[:2] == ["docker", "run"]:
            mounts = [a for a in argv if a.endswith(":ro")]
            root = Path(mounts[0].split(":")[0]).parent
            self.snapshot = {str(p.relative_to(root)): p.read_text() if p.is_file() and not p.is_symlink() else "<link>"
                             for p in root.rglob("*") if p.is_file() or p.is_symlink()}
        return self.result


@pytest.fixture
def ws(tmp_path):
    w = tmp_path / "ws"
    (w / "app").mkdir(parents=True)
    (w / "app/main.py").write_text("app = 1")
    return w


def test_run_stages_pristine_tests_and_strips_planted_hooks(ws):
    (ws / "conftest.py").write_text("planted")
    (ws / "tests").mkdir()
    (ws / "tests/conftest.py").write_text("planted")
    (ws / "tests/test_1.py").write_text("def test_x():\n    pass  # implementer edit\n")
    (ws / ".env").write_text("SECRET=1")
    rec = Recorder()
    DockerSandbox(rec).run(ws, [tc(1, code="def test_x():\n    assert True\n")], "docker-api")
    snap = rec.snapshot
    assert snap["work/app/main.py"] == "app = 1"
    assert snap["tests/tests/test_1.py"] == "def test_x():\n    assert True\n"  # bank version wins
    assert not any("conftest" in k or k.endswith(".env") for k in snap)


def test_symlinks_are_not_followed_into_the_host(ws, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("host secret")
    os.symlink(secret, ws / "leak.txt")
    rec = Recorder()
    DockerSandbox(rec).run(ws, [tc(1)], "docker-api")
    assert rec.snapshot["work/leak.txt"] == "<link>"
    assert "host secret" not in json.dumps(rec.snapshot)


def test_container_is_always_removed_even_on_timeout(ws):
    rec = Recorder(ExecResult(124, "", timed_out=True))
    rep = DockerSandbox(rec).run(ws, [tc(1)], "docker-api")
    assert rep.timed_out and rep.results == []
    assert rec.calls[-1][:3] == ["docker", "rm", "-f"]


def test_boot_failure_is_reported_not_raised(ws):
    rep = DockerSandbox(Recorder(ExecResult(3, "SHARLEY_BOOT_FAILED\nImportError: x"))).run(ws, [tc(1)], "docker-api")
    assert rep.boot_ok is False and "ImportError" in rep.build_output


def test_missing_docker_is_a_clean_failure(ws):
    sb = DockerSandbox(lambda a, t: ExecResult(127, "", "docker not installed"))
    assert sb.health() is False
    assert sb.run(ws, [tc(1)], "docker-api").boot_ok is False


def test_results_come_from_parser(ws):
    rep = DockerSandbox(Recorder()).run(ws, [tc(1), tc(2)], "docker-api")
    assert [r.passed for r in rep.results] == [True, False]


def test_workspace_cleanup_leaves_no_staging_dirs(ws):
    before = set(Path(os.environ.get("TMPDIR", "/tmp")).glob("sharley-run-*"))
    DockerSandbox(Recorder()).run(ws, [tc(1)], "docker-api")
    assert set(Path(os.environ.get("TMPDIR", "/tmp")).glob("sharley-run-*")) == before


# ---- real docker (CI has docker; locally skipped when the daemon is down)
def _docker_up():
    return shutil.which("docker") and subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@pytest.fixture(scope="module")
def real_sandbox():
    if not _docker_up():
        pytest.skip("docker unavailable")
    img = Path(__file__).resolve().parents[2] / "sharley/runner/images"
    subprocess.run(["docker", "build", "-q", "-f", str(img / "python.Dockerfile"), "-t", "sharley-runner-py:latest", str(img)],
                   check=True, capture_output=True)
    return DockerSandbox()


APP = "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\ndef h(): return {'ok': True}\n@app.get('/n')\ndef n(): return {'n': 1}\n"
HTTP_OK = "import os, httpx\ndef test_n():\n    assert httpx.get(os.environ['BASE_URL'] + '/n').json() == {'n': 1}\n"
HTTP_BAD = "import os, httpx\ndef test_n():\n    assert httpx.get(os.environ['BASE_URL'] + '/n').json() == {'n': 2}\n"
NET = ("import socket\ndef test_no_internet():\n    s = socket.socket(); s.settimeout(3)\n"
       "    try:\n        s.connect(('1.1.1.1', 53))\n    except OSError:\n        return\n    raise RuntimeError('network reachable')\n")
WRITE_ROOT = "def test_root_is_read_only():\n    try:\n        open('/etc/pwned', 'w')\n    except OSError:\n        return\n    raise RuntimeError('rootfs writable')\n"


@pytest.mark.docker
def test_real_sandbox_runs_pass_fail_and_blocks_network_and_root_writes(tmp_path, real_sandbox):
    (tmp_path / "app").mkdir()
    (tmp_path / "app/main.py").write_text(APP)
    tests = [tc(1, code=HTTP_OK), tc(2, code=HTTP_BAD), tc(3, code=NET), tc(4, code=WRITE_ROOT)]
    rep = real_sandbox.run(tmp_path, tests, "docker-api", timeout_s=120)
    got = {r.test_id: (r.passed, r.kind) for r in rep.results}
    assert got == {"T1": (True, "pass"), "T2": (False, "assert"), "T3": (True, "pass"), "T4": (True, "pass")}


@pytest.mark.docker
def test_real_sandbox_reports_boot_failure(tmp_path, real_sandbox):
    (tmp_path / "app").mkdir()
    (tmp_path / "app/main.py").write_text("raise SystemExit(1)")
    rep = real_sandbox.run(tmp_path, [tc(1, code=HTTP_OK)], "docker-api", timeout_s=120)
    assert rep.boot_ok is False
