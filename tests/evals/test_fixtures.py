import json
from pathlib import Path

import pytest

from evals.fixtures import build
from evals.reference import APP_DIR
from sharley.runner.base import RunReport, Sandbox, TestResult


class OracleLike(Sandbox):
    """Reference passes everything; the wrong implementation fails the R8 file; a mutant dies once a suite has 8+ tests."""
    name = "oracle-like"

    def health(self):
        return True

    def run(self, workspace, tests, stack, *, timeout_s=180):
        ws = str(workspace)
        def passes(t):
            if t.file.endswith("test_flaky.py"):
                return False
            if Path(workspace) == APP_DIR:
                return True
            if "sharley-mut-" in ws:
                return len(tests) < 8
            return "r8" not in t.name  # the buggy submission lacks ownership checks
        return RunReport(results=[TestResult(test_id=t.id, passed=passes(t), kind="pass" if passes(t) else "assert") for t in tests])


def test_tests_for_unlocks_subsets_by_rule():
    base = {t.name for t in build.tests_for([])}
    assert len(base) == 6 and not any("r8" in n for n in base)
    rules = list(build.UNLOCKS)
    assert any("r8" in t.name for t in build.tests_for(rules[:1]))
    assert any(t.file.endswith("test_flaky.py") for t in build.tests_for(rules))


def test_buggy_submission_really_differs_from_reference(tmp_path):
    impl = build.buggy_submission(tmp_path, 7)
    assert "if False:" in (impl / "app/notes.py").read_text()
    assert "if False:" not in (APP_DIR / "app/notes.py").read_text()


def test_build_demo_shape_and_honest_labelling():
    demo = build.build_demo(OracleLike(), workers=2)
    assert set(demo) == {"meta", "spec", "spec_text", "bank", "events", "eval", "timeline"}
    assert demo["meta"]["source"] == "oracle-stand-in" and "stand-in" in demo["meta"]["note"]
    assert demo["events"][-1]["type"] == "verdict"
    assert demo["bank"]["sealed"] and all(set(t) == {"index", "family", "locked"} for t in demo["bank"]["sealed"])
    decisions = [v["decision"] for v in demo["timeline"]]
    assert decisions[0] == "baseline" and "adopted" in decisions
    assert demo["eval"]["mutants"] and set(demo["eval"]["scores"]) >= {"heldout_mutation_score", "production_worthy"}


def test_sealed_code_never_enters_the_fixture():
    demo = build.build_demo(OracleLike(), workers=2)
    blob = json.dumps({k: demo[k] for k in ("bank", "events", "timeline", "eval")})
    from evals.reference import oracle_tests
    from sharley.judge import split_bank
    bank = split_bank(oracle_tests(), demo["spec"]["spec_hash"], 7)
    verdict_hint = demo["events"][-1]["verdict"]["hint"]
    for t in bank.sealed:
        assert t.name not in blob and t.file not in blob and t.code not in blob
        if t.hint != verdict_hint:  # only the failing test's plain-English hint is ever revealed
            assert t.hint not in blob


def test_committed_fixture_if_present_is_well_formed():
    f = Path(build.OUT)
    if not f.exists():
        pytest.skip("fixture not built yet")
    demo = json.loads(f.read_text())
    assert demo["meta"]["source"] and demo["timeline"][0]["decision"] == "baseline"
    assert any(v["decision"] == "rolled_back" and v["reason"] for v in demo["timeline"])
    assert demo["eval"]["reference"]["failed"] == 0
