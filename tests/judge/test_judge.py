from pathlib import Path

import pytest

from sharley.judge import (IndependenceError, LeakError, check_tamper, export_workspace, find_leaks, judge,
                           load_bank, ordered_sealed, safe_hint, save_bank, split_bank)
from sharley.runner.base import RunReport, Sandbox, TestResult
from sharley.schemas import ModelRef, TestCase
from sharley.storage import JsonRepository

IMPL = ModelRef(provider="gemini", model="gemini-4-argon", family="google")
VER = ModelRef(provider="meta", model="m", family="meta")


def mk(n, family="functional", req="R1", hint="users can read each other's notes"):
    return TestCase(id=f"T{n}", requirement_ids=[req], name=f"n{n}", family=family, file=f"tests/test_{n}.py",
                    code=f"def test_{n}():\n    assert api() == {n}  # SECRET-{n}\n", hint=hint)


def make_tests(n=20):
    return [mk(i, family="security" if i % 4 == 0 else "functional", req=f"R{i % 5 + 1}") for i in range(1, n + 1)]


class FakeSandbox(Sandbox):
    name = "fake"

    def __init__(self, fail=None, kind="assert", **report):
        self.fail, self.kind, self.report, self.calls = fail or set(), kind, report, []

    def health(self):
        return True

    def run(self, workspace, tests, stack, *, timeout_s=180):
        self.calls.append(tests)
        if self.report:
            return RunReport(**self.report)
        return RunReport(results=[TestResult(test_id=t.id, passed=t.id not in self.fail,
                                             kind="pass" if t.id not in self.fail else self.kind) for t in tests])


@pytest.fixture
def bank():
    return split_bank(make_tests(), "spechash", seed=7)


def j(bank, ws, sandbox, **kw):
    return judge(bank=bank, workspace=ws, sandbox=sandbox, stack="docker-api", implementer=IMPL, verifier=VER, **kw)


@pytest.fixture
def ws(bank, tmp_path):
    export_workspace(bank, tmp_path / "ws")
    return tmp_path / "ws"


# ---- split
def test_split_is_deterministic_and_roughly_30_70(bank):
    again = split_bank(make_tests(), "spechash", seed=7)
    assert [t.visibility for t in bank.tests] == [t.visibility for t in again.tests]
    assert 4 <= len(bank.examples) <= 8 and len(bank.sealed) >= 12


def test_different_seeds_pick_different_examples():
    a = {t.id for t in split_bank(make_tests(), "h", 1).examples}
    b = {t.id for t in split_bank(make_tests(), "h", 2).examples}
    assert a != b


def test_every_family_keeps_a_sealed_test_even_when_tiny():
    b = split_bank([mk(1), mk(2), mk(3, family="security")], "h", 1)
    assert {t.family for t in b.sealed} == {"functional", "security"}
    assert split_bank([mk(1)], "h", 1).sealed[0].id == "T1"
    singles = split_bank([mk(1), mk(2, family="security")], "h", 1)  # all-singleton families
    assert len(singles.examples) == 1 and len(singles.sealed) == 1


def test_sealed_order_is_stable_but_not_id_order(bank):
    order = [t.id for t in ordered_sealed(bank)]
    assert order == [t.id for t in ordered_sealed(bank)]
    assert order != sorted(order, key=lambda i: int(i[1:]))


# ---- workspace export and leak scan
def test_export_writes_examples_only(bank, tmp_path):
    written = export_workspace(bank, tmp_path / "w", "stack: x\n")
    assert sorted(written) == sorted(t.file for t in bank.examples)
    on_disk = {p.relative_to(tmp_path / "w").as_posix() for p in (tmp_path / "w").rglob("*") if p.is_file()}
    assert not on_disk & {t.file for t in bank.sealed}
    assert (tmp_path / "w/sharley.yaml").exists() and (tmp_path / "w/SHARLEY.md").exists()
    assert find_leaks(tmp_path / "w", bank) == []


def test_leak_scan_catches_sealed_code_pasted_anywhere(bank, ws):
    sealed = bank.sealed[0]
    (ws / "notes.txt").write_text("copied: " + sealed.code)
    assert sealed.id in find_leaks(ws, bank)


def test_leak_scan_catches_sealed_filename(bank, ws):
    sealed = bank.sealed[0]
    (ws / sealed.file).parent.mkdir(parents=True, exist_ok=True)
    (ws / sealed.file).write_text("x")
    assert sealed.id in find_leaks(ws, bank)


def test_export_refuses_when_an_example_duplicates_sealed_code_path(bank, tmp_path):
    from sharley.schemas import TestBank
    ex, sealed = bank.examples[0], bank.sealed[0]
    clash = sealed.model_copy(update={"file": ex.file})  # sealed test shares an example's path
    b2 = TestBank(spec_hash="h", seed=1, tests=[ex.model_copy(update={"code": "def test_ex():\n    pass\n"}), clash])
    with pytest.raises(LeakError):
        export_workspace(b2, tmp_path / "w2")


# ---- tamper
def test_untouched_workspace_has_no_tamper_issues(bank, ws):
    assert check_tamper(ws, bank) == []


def test_edit_delete_and_skip_are_detected(bank, ws):
    ex = bank.examples
    (ws / ex[0].file).write_text("def test_x():\n    pass\n")
    (ws / ex[1].file).unlink()
    (ws / "conftest.py").write_text("import pytest\ndef pytest_collection_modifyitems(items):\n    [i.add_marker(pytest.mark.skip) for i in items]\n")
    issues = check_tamper(ws, bank)
    assert any("edited" in i for i in issues) and any("deleted" in i for i in issues) and any("skip" in i for i in issues)


def test_harmless_conftest_is_not_flagged(bank, ws):
    (ws / "conftest.py").write_text("import pytest\n@pytest.fixture\ndef client(): ...\n")
    assert check_tamper(ws, bank) == []


# ---- verdicts
def test_accepted_when_all_sealed_pass(bank, ws):
    v = j(bank, ws, FakeSandbox())
    assert v.status == "Accepted" and v.example_passed == v.example_total == len(bank.examples)
    assert v.total_sealed == len(bank.sealed)


def test_leetcode_demo_moment_examples_pass_but_sealed_fails(bank, ws):
    target = ordered_sealed(bank)[4]
    v = j(bank, ws, FakeSandbox(fail={target.id}))
    assert v.status == "Wrong Answer" and v.failed_test_index == 5
    assert v.requirement_ids == target.requirement_ids and v.example_passed == v.example_total
    assert "sealed test 5 of" in v.summary() and "SECRET" not in v.summary()


def test_first_failing_sealed_test_is_reported(bank, ws):
    order = ordered_sealed(bank)
    v = j(bank, ws, FakeSandbox(fail={order[9].id, order[3].id}))
    assert v.failed_test_index == 4


def test_runtime_error_boot_failure_and_timeout(bank, ws):
    first = ordered_sealed(bank)[0]
    assert j(bank, ws, FakeSandbox(fail={first.id}, kind="runtime")).status == "Runtime Error"
    assert j(bank, ws, FakeSandbox(boot_ok=False, build_output="ImportError: nope")).status == "Build Failed"
    assert j(bank, ws, FakeSandbox(timed_out=True)).status == "Time Limit Exceeded"


def test_tampered_workspace_is_rejected_without_running_sealed_tests(bank, ws):
    (ws / bank.examples[0].file).write_text("def test_x(): pass")
    sb = FakeSandbox()
    v = j(bank, ws, sb)
    assert v.status == "Rejected: tests tampered" and "edited" in v.hint and sb.calls == []


def test_sandbox_receives_bank_tests_not_workspace_copies(bank, ws):
    sb = FakeSandbox()
    j(bank, ws, sb)
    assert {t.id for t in sb.calls[0]} == {t.id for t in bank.tests}


def test_missing_results_count_as_failures(bank, ws):
    v = j(bank, ws, FakeSandbox(results=[]))
    assert v.status == "Runtime Error" and v.failed_test_index == 1


def test_same_model_family_is_refused_before_any_run(bank, ws):
    sb = FakeSandbox()
    with pytest.raises(IndependenceError):
        judge(bank=bank, workspace=ws, sandbox=sb, stack="docker-api", implementer=VER, verifier=VER)
    assert sb.calls == []


def test_verdict_records_models_seed_and_spec_hash_and_persists(bank, ws, tmp_path):
    repo = JsonRepository(tmp_path / "db")
    v = j(bank, ws, FakeSandbox(), repo=repo, run_id="run1")
    assert (v.implementer, v.verifier, v.seed, v.spec_hash) == (IMPL, VER, 7, "spechash")
    assert repo.get("verdicts", "run1")["status"] == "Accepted"


# ---- hint hygiene
@pytest.mark.parametrize("hint", ["assert resp.status_code == 403", "`secret_token` leaks", "def test_x(): ...",
                                  "client.get('/notes') returns 200", ""])
def test_code_shaped_hints_never_reach_the_implementer(hint):
    assert safe_hint(hint, ["R7"]) == "behaviour required by R7 is not met"


def test_plain_hint_kept_whole_up_to_the_cap_and_cut_on_a_word_boundary():
    assert safe_hint("users can read each other's notes", ["R7"]) == "users can read each other's notes"
    real = ("Run billing for the seeded month 2026-02 and, for every residential A and B house, check its billed cents equals "
            "its kWh used times 12 or 18 (within one cent of rounding). A mismatch shows the wrong rate was applied or the charge disagrees")
    assert safe_hint(real, ["R1"]) == real  # ~255 chars: must not be truncated
    long = "word " * 100
    out = safe_hint(long, ["R1"])
    assert out.endswith("...") and len(out) <= 323 and not out.removesuffix("...").endswith("wor")  # whole words only


# ---- storage
def test_bank_roundtrips_through_repository(bank, tmp_path):
    repo = JsonRepository(tmp_path)
    key = save_bank(repo, bank)
    assert load_bank(repo, key) == bank
    with pytest.raises(KeyError):
        load_bank(repo, "nope")
