import json
from pathlib import Path

import pytest

from sharley.harness import FallbackChain
from sharley.implementer import implement, safe_target
from sharley.judge import export_workspace, split_bank
from sharley.runner.base import RunReport, Sandbox, TestResult
from sharley.schemas import TestCase
from tests.fakes import ScriptedProvider


def case(i, fam="functional"):
    return TestCase(id=f"T{i}", requirement_ids=["R1"], name="n", family=fam, file=f"tests/test_{i}.py",
                    code=f"def test_{i}():\n    assert True  # SEALED-SECRET-{i}\n")


class AppSandbox(Sandbox):
    """Examples pass once app/main.py contains 'GOOD'."""
    name = "fake"

    def __init__(self):
        self.runs = 0

    def health(self):
        return True

    def run(self, workspace, tests, stack, *, timeout_s=180):
        self.runs += 1
        main = workspace / "app/main.py"
        ok = main.exists() and "GOOD" in main.read_text()
        return RunReport(results=[TestResult(test_id=t.id, passed=ok, kind="pass" if ok else "assert",
                                             output="" if ok else "assert 404 == 200") for t in tests])


def files(*pairs):
    return json.dumps({"files": [{"path": p, "content": c} for p, c in pairs]})


@pytest.fixture
def setup(tmp_path):
    bank = split_bank([case(i) for i in range(1, 11)], "h", 1)
    ws = tmp_path / "ws"
    export_workspace(bank, ws, "stack: docker-api\n")
    return bank, ws


def test_implementer_iterates_on_example_failures_until_green(setup):
    bank, ws = setup
    p = ScriptedProvider("impl", [files(("app/main.py", "BAD")), files(("app/main.py", "GOOD"))])
    sb = AppSandbox()
    res = implement(FallbackChain([p]), bank, ws, sb, "docker-api", "build notes")
    assert res.rounds == 2 and res.example_passed == res.example_total == len(bank.examples)
    assert "assert 404 == 200" in p.calls[1][1]  # second round saw the example failure


def test_implementer_never_sees_sealed_tests(setup):
    bank, ws = setup
    p = ScriptedProvider("impl", [files(("app/main.py", "GOOD"))])
    implement(FallbackChain([p]), bank, ws, AppSandbox(), "docker-api", "build notes")
    prompt = p.calls[0][1]
    assert all(f"SEALED-SECRET-{t.id[1:]}" not in prompt for t in bank.sealed)
    assert any(f"SEALED-SECRET-{t.id[1:]}" in prompt for t in bank.examples)


def test_stops_after_round_limit(setup):
    bank, ws = setup
    p = ScriptedProvider("impl", [files(("app/main.py", "BAD"))] * 5)
    res = implement(FallbackChain([p]), bank, ws, AppSandbox(), "docker-api", "t", rounds=2)
    assert res.rounds == 2 and res.example_passed == 0 and len(p.calls) == 2


@pytest.mark.parametrize("path", ["../escape.py", "/etc/cron.d/x", "tests/test_1.py", "tests/conftest.py", ".env",
                                  "sub/.env.local", "sharley.yaml", "a/../../b.py", ""])
def test_hostile_paths_are_refused(setup, path):
    bank, ws = setup
    p = ScriptedProvider("impl", [files((path, "evil"), ("app/main.py", "GOOD"))])
    res = implement(FallbackChain([p]), bank, ws, AppSandbox(), "docker-api", "t")
    assert path in res.rejected and path not in res.written
    assert not (ws.parent / "escape.py").exists()
    ex = bank.examples[0]
    assert (ws / ex.file).read_text() == ex.code  # example tests untouched


def test_oversized_files_are_refused(setup):
    bank, ws = setup
    p = ScriptedProvider("impl", [files(("app/big.py", "x" * 120_000), ("app/main.py", "GOOD"))])
    res = implement(FallbackChain([p]), bank, ws, AppSandbox(), "docker-api", "t")
    assert "app/big.py" in res.rejected


def test_symlink_escape_is_refused(setup, tmp_path):
    bank, ws = setup
    (ws / "link").symlink_to(tmp_path)
    assert safe_target(ws, "link/pwned.py", "tests") is None


def test_boot_failure_is_fed_back(setup):
    bank, ws = setup

    class Boot(AppSandbox):
        def run(self, workspace, tests, stack, *, timeout_s=180):
            self.runs += 1
            if self.runs == 1:
                return RunReport(boot_ok=False, build_output="ImportError: no module app")
            return super().run(workspace, tests, stack, timeout_s=timeout_s)

    p = ScriptedProvider("impl", [files(("app/main.py", "BAD")), files(("app/main.py", "GOOD"))])
    res = implement(FallbackChain([p]), bank, ws, Boot(), "docker-api", "t")
    assert "ImportError" in p.calls[1][1] and res.rounds == 2
