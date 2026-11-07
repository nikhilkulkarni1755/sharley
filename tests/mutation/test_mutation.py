import ast
from pathlib import Path

import pytest

from evals.graders import false_failure_rate, mutation_score, score, security_kill_rate
from evals.reference import APP_DIR
from sharley.mutation import OPERATORS, apply_mutant, evaluate, generate_mutants, run_mutant
from sharley.mutation.operators import (drop_owner_filter, flip_conditional, leak_stack_trace, off_by_one,
                                        remove_auth_check, skip_password_check, string_concat_sql, wrong_status_code)
from sharley.runner.base import RunReport, Sandbox, TestResult
from sharley.schemas import Mutant, TestCase


# ---- operators: applies where it should, declines elsewhere
@pytest.mark.parametrize("line,expected", [
    ("    if len(password) < 8:", "    if len(password) <= 8:"),
    ("    if attempts >= MAX_ATTEMPTS:  # mut:ratelimit", "    if attempts > MAX_ATTEMPTS:  # mut:ratelimit"),
    ("    return a > b", "    return a >= b"),
])
def test_off_by_one(line, expected):
    assert off_by_one(line) == expected


@pytest.mark.parametrize("line", ["    x = a < b", "def f() -> dict:", "    foo(a)", "    if a == b:  # >= comment"])
def test_off_by_one_declines_non_comparisons(line):
    assert off_by_one(line) is None or ">=" not in off_by_one(line).split("#")[0]


def test_flip_conditional_variants():
    assert flip_conditional("    if a == b:") == "    if a != b:"
    assert flip_conditional("    if a and b:") == "    if a or b:"
    assert flip_conditional("    if not ok:") == "    if ok:"
    assert flip_conditional("    x = a == b") is None


def test_wrong_status_code():
    assert wrong_status_code('raise HTTPException(status_code=404, detail="x")') == 'raise HTTPException(status_code=403, detail="x")'
    assert wrong_status_code("status_code=500") is None and wrong_status_code("no status") is None


def test_security_operators_on_sample_lines():
    assert remove_auth_check("    user = auth.require_user(request)  # mut:auth") == \
        '    user = {"id": 1, "username": "anon"}  # mut:auth'
    assert leak_stack_trace('content={"detail": "internal error"})  # mut:trace') == \
        "content={\"detail\": traceback.format_exc()})  # mut:trace"
    line = '    if row is None or not secrets.compare_digest(a, hash_password(p, row["salt"])):  # mut:credcheck'
    assert skip_password_check(line) == "    if row is None:  # mut:credcheck"


def test_string_concat_sql_inlines_last_param_and_stays_valid_python():
    line = '    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()  # mut:sql'
    out = string_concat_sql(line)
    assert "{username}" in out and "?" not in out
    ast.parse(out.strip())
    multi = '    rows = db.execute("SELECT * FROM notes WHERE user_id = ? AND title LIKE ? ORDER BY id", (user["id"], f"%{q}%")).fetchall()'
    out2 = string_concat_sql(multi)
    assert 'user_id = ?' in out2 and "LIKE '{" in out2
    ast.parse(out2.strip())


def test_drop_owner_filter_removes_param_and_clause():
    line = '    rows = db.execute("SELECT * FROM notes WHERE user_id = ? AND title LIKE ? ORDER BY id", (user["id"], f"%{q}%")).fetchall()'
    out = drop_owner_filter(line)
    assert "1 = 1 AND" in out and 'user["id"]' not in out
    ast.parse(out.strip())
    assert drop_owner_filter('db.execute("SELECT 1 WHERE a = ?", (a,))') is None


def test_every_operator_has_a_category():
    assert {o.category for o in OPERATORS} == {"functional", "security"}
    assert {o.name for o in OPERATORS if o.category == "security"} >= {
        "remove_auth_check", "string_concat_sql", "missing_ownership_check", "leak_stack_trace", "disable_rate_limit"}


# ---- generation on the real reference app
@pytest.fixture(scope="module")
def mutants():
    return generate_mutants(APP_DIR, seed=3)


def test_enough_mutants_with_every_operator_present(mutants):
    assert len(mutants) >= 30
    assert {m.operator for m in mutants} == {o.name for o in OPERATORS}


def test_ids_unique_sequential_and_generation_deterministic(mutants):
    assert [m.id for m in mutants] == [f"M{i:03d}" for i in range(1, len(mutants) + 1)]
    assert [m.model_dump() for m in generate_mutants(APP_DIR, seed=3)] == [m.model_dump() for m in mutants]


def test_split_is_roughly_60_40_and_security_in_both(mutants):
    held = [m for m in mutants if m.split == "heldout"]
    assert 0.3 <= len(held) / len(mutants) <= 0.5
    assert {m.category for m in held} == {"functional", "security"}
    assert {m.category for m in mutants if m.split == "train"} == {"functional", "security"}


def test_seed_changes_which_mutants_are_heldout():
    a = {m.id for m in generate_mutants(APP_DIR, seed=1) if m.split == "heldout"}
    b = {m.id for m in generate_mutants(APP_DIR, seed=2) if m.split == "heldout"}
    assert a != b


def test_every_mutant_is_valid_python_and_actually_different(mutants, tmp_path):
    for i, m in enumerate(mutants):
        assert m.mutated != m.original
        dest = apply_mutant(APP_DIR, m, tmp_path / f"m{i}")
        ast.parse((dest / m.file).read_text())


def test_original_app_is_never_modified(mutants, tmp_path):
    before = (APP_DIR / mutants[0].file).read_text()
    apply_mutant(APP_DIR, mutants[0], tmp_path / "x")
    assert (APP_DIR / mutants[0].file).read_text() == before


def test_stale_and_escaping_mutants_are_refused(mutants, tmp_path):
    stale = mutants[0].model_copy(update={"original": "something else"})
    with pytest.raises(ValueError, match="stale"):
        apply_mutant(APP_DIR, stale, tmp_path / "a")
    evil = mutants[0].model_copy(update={"file": "../../../etc/passwd"})
    with pytest.raises(ValueError, match="escapes"):
        apply_mutant(APP_DIR, evil, tmp_path / "b")


# ---- evaluation + graders with a fake sandbox
def case(i):
    return TestCase(id=f"T{i}", requirement_ids=["R1"], name="n", family="functional", file=f"tests/t{i}.py", code="x")


class Fake(Sandbox):
    name = "fake"

    def __init__(self, kill=lambda ws: False, boot=lambda ws: True, ref_fail=0):
        self.kill, self.boot, self.ref_fail = kill, boot, ref_fail

    def health(self):
        return True

    def run(self, workspace, tests, stack, *, timeout_s=180):
        is_ref = Path(workspace) == APP_DIR
        fails = self.ref_fail if is_ref else (1 if self.kill(workspace) else 0)
        return RunReport(boot_ok=self.boot(workspace),
                         results=[TestResult(test_id=t.id, passed=i >= fails, kind="pass" if i >= fails else "assert")
                                  for i, t in enumerate(tests)])


def mk(i, split, cat="functional", killed=None):
    return Mutant(id=f"M{i}", operator="o", category=cat, file="f", line=1, original="a", mutated="b", split=split, killed=killed)


def test_graders_ignore_unbootable_and_other_splits():
    ms = [mk(1, "heldout", killed=True), mk(2, "heldout", killed=False), mk(3, "heldout", killed=None),
          mk(4, "train", killed=True)]
    assert mutation_score(ms, "heldout") == 0.5
    assert mutation_score(ms, "train") == 1.0 and mutation_score(ms, None) == pytest.approx(2 / 3)
    assert mutation_score([], "heldout") == 0.0


def test_security_kill_rate_counts_only_security():
    ms = [mk(1, "train", "security", True), mk(2, "train", "security", False), mk(3, "train", "functional", False)]
    assert security_kill_rate(ms) == 0.5


def test_false_failure_rate_on_reference():
    ok = RunReport(results=[TestResult(test_id="a", passed=True, kind="pass"), TestResult(test_id="b", passed=False, kind="assert")])
    assert false_failure_rate(ok) == 0.5
    assert false_failure_rate(RunReport(boot_ok=False)) == 1.0
    assert false_failure_rate(RunReport(timed_out=True)) == 1.0
    assert false_failure_rate(RunReport()) == 1.0


def test_evaluate_marks_killed_survived_and_invalid(mutants):
    sample = mutants[:3]
    first = sample[0]

    def kill(ws):  # kill only the first mutant (identified by its mutated line on disk)
        return first.mutated in (Path(ws) / first.file).read_text()

    def boot(ws):  # third mutant fails to boot
        return sample[2].mutated not in (Path(ws) / sample[2].file).read_text()

    res = evaluate(Fake(kill=kill, boot=boot), APP_DIR, [case(1), case(2)], sample, workers=2)
    assert [m.killed for m in res.mutants] == [True, False, None]
    s = score(res, split=None)
    assert s.heldout_mutation_score == 0.5 and s.false_failure_rate == 0.0


def test_timeout_counts_as_kill(mutants):
    class Slow(Fake):
        def run(self, workspace, tests, stack, *, timeout_s=180):
            return RunReport(timed_out=Path(workspace) != APP_DIR, results=[] if Path(workspace) != APP_DIR else [
                TestResult(test_id="T1", passed=True, kind="pass")])

    assert run_mutant(Slow(), APP_DIR, [case(1)], mutants[0], "docker-api", 5).killed is True


def test_production_worthy_threshold_arithmetic():
    res = evaluate(Fake(kill=lambda ws: True, ref_fail=1), APP_DIR, [case(1), case(2), case(3), case(4)], [], workers=1)
    s = score(res)
    assert s.false_failure_rate == 0.25 and s.production_worthy == s.heldout_mutation_score * 0.75


# ---- real Docker: the oracle suite has teeth
@pytest.mark.docker
def test_oracle_kills_security_mutants_and_spares_the_correct_app():
    import shutil
    import subprocess

    from evals.reference import oracle_tests
    from sharley.runner import DockerSandbox

    if not shutil.which("docker") or subprocess.run(["docker", "info"], capture_output=True).returncode:
        pytest.skip("docker unavailable")
    img = Path(__file__).resolve().parents[2] / "sharley/runner/images"
    subprocess.run(["docker", "build", "-q", "-f", str(img / "python.Dockerfile"), "-t", "sharley-runner-py:latest", str(img)],
                   check=True, capture_output=True)
    ms = generate_mutants(APP_DIR, seed=0)
    pick = {name: next(m for m in ms if m.operator == name) for name in
            ("remove_auth_check", "missing_ownership_check", "disable_rate_limit", "leak_stack_trace")}
    equivalent = next(m for m in ms if m.operator == "string_concat_sql" and m.file == "app/notes.py"
                      and "WHERE id = ?" in m.original)  # int-typed path param: injection impossible
    res = evaluate(DockerSandbox(), APP_DIR, oracle_tests(), [*pick.values(), equivalent], workers=3)
    assert res.reference.boot_ok and all(r.passed for r in res.reference.results)  # false failure rate 0
    killed = {m.id: m.killed for m in res.mutants}
    assert all(killed[m.id] is True for m in pick.values()), killed
    assert killed[equivalent.id] is False  # equivalent mutant survives: filtered out of the eval set later
