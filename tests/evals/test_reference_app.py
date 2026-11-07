import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from evals.reference import APP_DIR, SPEC_TEXT, oracle_tests, reference_spec
from sharley.planner import trace


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_app(tmp_path_factory):
    port = free_port()
    env = {**os.environ, "NOTES_DB": str(tmp_path_factory.mktemp("db") / "n.db")}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=APP_DIR,
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            if httpx.get(base + "/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("reference app did not boot")
    yield base
    proc.terminate()


def test_spec_is_valid_with_one_explicit_assumption():
    spec = reference_spec()
    assert len(spec.requirements) == 12
    inferred = [r.id for r in spec.requirements if r.evidence.kind == "inferred"]
    assert inferred == ["R11"] and spec.assumptions["A1"]
    for r in spec.requirements:
        if r.evidence.kind == "observed":
            assert r.evidence.source_span.lower() in " ".join(SPEC_TEXT.lower().split())


def test_oracle_traces_every_requirement():
    assert trace(reference_spec(), oracle_tests()).ok


@pytest.mark.parametrize("case", oracle_tests(), ids=lambda t: t.name)
def test_correct_app_passes_every_oracle_file(live_app, case, tmp_path):
    f = tmp_path / case.file.split("/")[-1]
    f.write_text(case.code)
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-c", "/dev/null", "-p", "no:cacheprovider", str(f)],
                       env={**os.environ, "BASE_URL": live_app}, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-1500:]


# ---- app behaviours the oracle does not cover
def test_password_hash_is_salted_pbkdf2():
    sys.path.insert(0, str(APP_DIR))
    os.environ["NOTES_DB"] = ":memory:"
    try:
        from app import auth
        assert auth.hash_password("pw", "00" * 16) != auth.hash_password("pw", "01" * 16)
        assert auth.hash_password("pw", "00" * 16) == auth.hash_password("pw", "00" * 16)
        assert "pw" not in auth.hash_password("pw", "00" * 16)
    finally:
        sys.path.remove(str(APP_DIR))
        for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
            del sys.modules[m]
