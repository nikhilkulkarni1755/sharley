import json
from io import StringIO

import pytest

from evals.improve import reference_files, run_improvement
from sharley.gate.cli import USAGE, main
from sharley.gate.context import Context
from sharley.gate.service import make_bank
from sharley.harness import FallbackChain
from sharley.mutation import generate_mutants
from sharley.runner.base import RunReport
from sharley.schemas import Evidence, Requirement, Scores, SkillVersion, Spec
from sharley.skills import SkillStore
from sharley.storage import JsonRepository
from tests.fakes import ScriptedProvider

GOOD = json.dumps({"tests": [{"name": "a", "code": "def test_a():\n    assert True\n", "requirement_ids": ["R1"]}]})
SPEC = Spec(source_hash="s", stack="docker-api", requirements=[
    Requirement(id="R1", text="Users can log in", category="functional", evidence=Evidence(kind="observed", source_span="x"))])
SC = Scores(heldout_mutation_score=0.5, false_failure_rate=0, security_kill_rate=0.5)


def adopt(store, rules, version=0):
    store.save(SkillVersion(version=version, parent=None if version == 0 else version - 1, rules=rules,
                            decision="baseline" if version == 0 else "adopted", scores=SC))


# ---- scopes
def test_scopes_are_isolated_and_overlay_on_global(tmp_path):
    repo = JsonRepository(tmp_path)
    adopt(SkillStore(repo), ["Test ownership on every resource."])
    adopt(SkillStore(repo, "acme"), ["Always test the acme billing cycle."])
    assert SkillStore(repo).active_rules() == ["Test ownership on every resource."]
    assert SkillStore(repo, "acme").active_rules() == ["Test ownership on every resource.", "Always test the acme billing cycle."]
    assert SkillStore(repo, "other").active_rules() == ["Test ownership on every resource."]  # acme's rules never leak
    assert [v.version for v in SkillStore(repo, "acme").timeline()] == [0]


def test_org_rules_are_deduplicated_against_global(tmp_path):
    repo = JsonRepository(tmp_path)
    adopt(SkillStore(repo), ["Same rule."])
    adopt(SkillStore(repo, "acme"), ["Same rule.", "Extra."])
    assert SkillStore(repo, "acme").active_rules() == ["Same rule.", "Extra."]


@pytest.mark.parametrize("bad", ["../x", "a b", "a/b", "", "$ne"])
def test_hostile_scope_names_are_refused(tmp_path, bad):
    with pytest.raises(ValueError):
        SkillStore(JsonRepository(tmp_path), bad)


# ---- the pipeline now uses what Sharley has learned
def test_make_bank_injects_adopted_rules_into_the_writer_prompt(tmp_path):
    repo = JsonRepository(tmp_path)
    adopt(SkillStore(repo), ["Always test ownership on every resource endpoint."])
    p = ScriptedProvider("p", [GOOD])
    make_bank(SPEC, repo, FallbackChain([p]), workers=1, allow_partial=True)
    assert "Always test ownership on every resource endpoint." in p.calls[0][1]


def test_scope_overlay_reaches_only_that_scopes_banks(tmp_path):
    repo = JsonRepository(tmp_path)
    adopt(SkillStore(repo, "acme"), ["Acme-only rule about invoices."])
    mine, theirs = ScriptedProvider("a", [GOOD]), ScriptedProvider("b", [GOOD])
    make_bank(SPEC, repo, FallbackChain([mine]), workers=1, allow_partial=True, scope="acme")
    make_bank(SPEC, repo, FallbackChain([theirs]), workers=1, allow_partial=True, scope="globex")
    assert "Acme-only rule" in mine.calls[0][1] and "Acme-only rule" not in theirs.calls[0][1]


def test_rolled_back_rules_are_never_applied(tmp_path):
    repo = JsonRepository(tmp_path)
    store = SkillStore(repo)
    adopt(store, ["Good rule."])
    store.save(SkillVersion(version=1, parent=0, rules=["Good rule.", "Bad rule."], decision="rolled_back", reason="no gain"))
    assert store.active_rules() == ["Good rule."]


def test_explicit_empty_rules_still_override(tmp_path):
    repo = JsonRepository(tmp_path)
    adopt(SkillStore(repo), ["A rule."])
    p = ScriptedProvider("p", [GOOD])
    make_bank(SPEC, repo, FallbackChain([p]), workers=1, allow_partial=True, rules=[])
    assert "A rule." not in p.calls[0][1]


# ---- improve command wiring
def test_reference_files_exclude_the_oracle_tests():
    files = reference_files()
    assert "app/main.py" in files and not any(p.startswith("oracle/") for p in files)


def test_run_improvement_persists_to_the_requested_scope(tmp_path):
    from evals.reference import APP_DIR, oracle_tests
    from sharley.mutation import evaluate as ev
    import evals.improve as mod

    class Killer:
        name = "k"
        health = lambda self: True  # noqa: E731

        def run(self, workspace, tests, stack, *, timeout_s=180):
            from sharley.runner.base import TestResult
            kill = len(tests) >= 10 and workspace != APP_DIR
            return RunReport(results=[TestResult(test_id=t.id, passed=not kill, kind="assert" if kill else "pass") for t in tests])

    repo = JsonRepository(tmp_path)
    chain = FallbackChain([ScriptedProvider("p", [json.dumps({"rule": "Probe pagination boundaries on every list endpoint.", "rationale": "r"})])])
    ctx = Context(env={}, repo=repo, verifier=chain, long_context=FallbackChain([ScriptedProvider("s")]), sandbox=Killer())
    ms = generate_mutants(APP_DIR, seed=0)[:6]
    result = run_improvement(ctx, Killer(), scope="acme", iters=1, mutants=ms, generate=lambda rules: oracle_tests()[: 4 + 8 * len(rules)])
    assert [v.version for v in SkillStore(repo, "acme").timeline()] == [v.version for v in result.timeline]
    assert SkillStore(repo).timeline() == []  # global untouched


def test_improve_command_rejects_silly_iteration_counts(tmp_path):
    out = StringIO()
    ctx = Context(env={}, repo=JsonRepository(tmp_path), verifier=FallbackChain([ScriptedProvider("p")]),
                  long_context=FallbackChain([ScriptedProvider("s")]), sandbox=None)
    assert main(["improve", "--iters", "99"], env={}, out=out, context_factory=lambda e: ctx) == USAGE
    assert "between 1 and 5" in out.getvalue()
