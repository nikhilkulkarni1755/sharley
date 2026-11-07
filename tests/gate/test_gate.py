import json
from pathlib import Path

import pytest

from sharley.gate import IncompleteBank, check_submission, make_bank, publish_examples
from sharley.gate.cli import FAILED, INCOMPLETE, OK, USAGE, main
from sharley.gate.context import Context
from sharley.gate.report import exit_code, github_annotation, render
from sharley.harness import FallbackChain
from sharley.intake.files import load_codebase
from sharley.judge import find_leaks, load_bank
from sharley.runner.base import RunReport, Sandbox, TestResult
from sharley.schemas import Evidence, ModelRef, Requirement, Spec
from sharley.storage import JsonRepository
from tests.fakes import EchoWriter, ScriptedProvider

EXTRACT = json.dumps({"requirements": [
    {"text": "Users can create notes", "category": "functional", "source_span": "create notes"},
    {"text": "Users cannot read other notes", "category": "security", "source_span": "never read other notes"},
    {"text": "App serves a health check", "category": "deployment", "assumption": "deploy norm"}]})
SPEC_TEXT = "Users create notes and never read other notes."
IMPL = ModelRef(provider="external", model="argon", family="google")


class FakeSandbox(Sandbox):
    name = "fake"

    def __init__(self, fail_after=None, **report):
        self.fail_after, self.report, self.calls = fail_after, report, 0

    def health(self):
        return True

    def run(self, workspace, tests, stack, *, timeout_s=180):
        self.calls += 1
        if self.report:
            return RunReport(**self.report)
        return RunReport(results=[TestResult(test_id=t.id, passed=True, kind="pass") for t in tests])


def spec_obj():
    ev = Evidence(kind="observed", source_span="x")
    return Spec(source_hash="s", stack="docker-api", requirements=[
        Requirement(id=f"R{i}", text=f"Requirement {i}", category=c, evidence=ev)
        for i, c in enumerate(["functional", "functional", "security", "deployment"], 1)])


def ctx(tmp_path, sandbox=None, writer=None):
    chain = FallbackChain([writer or EchoWriter(EXTRACT)])
    return Context(env={}, repo=JsonRepository(tmp_path / "db"), verifier=chain,
                   long_context=FallbackChain([ScriptedProvider("subq")]), sandbox=sandbox or FakeSandbox())


# ---- service
def test_make_bank_records_author_splits_and_saves(tmp_path):
    c = ctx(tmp_path)
    bank = make_bank(spec_obj(), c.repo, c.verifier, seed=4)
    assert bank.author.family == "fake" and bank.examples and bank.sealed
    assert load_bank(c.repo, f"{bank.spec_hash}:4") == bank


def test_incomplete_bank_is_refused_unless_partial(tmp_path):
    spec = spec_obj()
    only_r1 = ScriptedProvider("p", [json.dumps({"tests": [{"name": "a", "code": "def test_a(): pass",
                                                            "requirement_ids": ["R1"]}]})] * 9)
    with pytest.raises(IncompleteBank) as e:
        make_bank(spec, JsonRepository(tmp_path / "a"), FallbackChain([only_r1]), stack="docker-api", workers=1)
    assert "R2" in e.value.report.uncovered


def test_published_workspace_has_examples_and_contract_but_nothing_sealed(tmp_path):
    c = ctx(tmp_path)
    bank = make_bank(spec_obj(), c.repo, c.verifier)
    written = publish_examples(bank, spec_obj(), tmp_path / "ws")
    assert sorted(written) == sorted(t.file for t in bank.examples)
    assert (tmp_path / "ws/sharley.yaml").exists() and find_leaks(tmp_path / "ws", bank) == []


def test_check_requires_recorded_verifier(tmp_path):
    c = ctx(tmp_path)
    bank = make_bank(spec_obj(), c.repo, c.verifier).model_copy(update={"author": None})
    with pytest.raises(ValueError, match="verifier"):
        check_submission(bank, tmp_path, FakeSandbox(), "docker-api", IMPL)


# ---- reports
def test_render_and_exit_codes(tmp_path):
    c = ctx(tmp_path)
    bank = make_bank(spec_obj(), c.repo, c.verifier)
    publish_examples(bank, spec_obj(), tmp_path / "ws")
    ok = check_submission(bank, tmp_path / "ws", FakeSandbox(), "docker-api", IMPL)
    assert exit_code(ok) == 0 and "Accepted" in render(ok) and github_annotation(ok) == ""
    bad = check_submission(bank, tmp_path / "ws", FakeSandbox(boot_ok=False, build_output="ImportError"), "docker-api", IMPL)
    assert exit_code(bad) == 1 and "Build Failed" in render(bad) and github_annotation(bad).startswith("::error")


# ---- CLI end to end
def run_cli(tmp_path, argv, c=None):
    from io import StringIO
    out = StringIO()
    code = main(argv, env={}, out=out, context_factory=lambda env: c or ctx(tmp_path))
    return code, out.getvalue()


def test_cli_spec_bank_check_flow(tmp_path):
    c = ctx(tmp_path)
    (tmp_path / "idea.txt").write_text(SPEC_TEXT)
    code, out = run_cli(tmp_path, ["spec", "--text", str(tmp_path / "idea.txt"), "--out", str(tmp_path / "spec.json")], c)
    assert code == OK and "3 requirements (2 observed, 1 inferred)" in out
    spec = Spec.model_validate_json((tmp_path / "spec.json").read_text())
    assert spec.stack is None

    code, out = run_cli(tmp_path, ["bank", "--spec", str(tmp_path / "spec.json"), "--workspace", str(tmp_path / "ws"),
                                   "--stack", "docker-api", "--bank-out", str(tmp_path / "bank.json")], c)
    assert code == OK and "sealed (hidden)" in out
    assert not any("sealed" in p.name for p in (tmp_path / "ws").rglob("*") if p.is_file())

    code, out = run_cli(tmp_path, ["check", "--bank-file", str(tmp_path / "bank.json"), "--workspace", str(tmp_path / "ws"),
                                   "--implementer-model", "argon", "--implementer-family", "google"], c)
    assert code == OK and "Accepted" in out


def test_cli_check_fails_the_build_with_plain_english(tmp_path):
    c = ctx(tmp_path, sandbox=FakeSandbox(boot_ok=False, build_output="ModuleNotFoundError: app"))
    bank = make_bank(spec_obj(), c.repo, c.verifier)
    publish_examples(bank, spec_obj(), tmp_path / "ws")
    code, out = run_cli(tmp_path, ["check", "--bank", f"{bank.spec_hash}:{bank.seed}", "--workspace", str(tmp_path / "ws"),
                                   "--implementer-model", "m", "--implementer-family", "google"], c)
    assert code == FAILED and "Build Failed" in out and "::error" in out


def test_cli_rejects_same_family_implementer(tmp_path):
    c = ctx(tmp_path)
    bank = make_bank(spec_obj(), c.repo, c.verifier)
    publish_examples(bank, spec_obj(), tmp_path / "ws")
    code, out = run_cli(tmp_path, ["check", "--bank", f"{bank.spec_hash}:{bank.seed}", "--workspace", str(tmp_path / "ws"),
                                   "--implementer-model", "same", "--implementer-family", "fake"], c)
    assert code == USAGE and "different model families" in out and c.sandbox.calls == 0


def test_cli_detects_tampered_example_tests(tmp_path):
    c = ctx(tmp_path)
    bank = make_bank(spec_obj(), c.repo, c.verifier)
    publish_examples(bank, spec_obj(), tmp_path / "ws")
    (tmp_path / "ws" / bank.examples[0].file).write_text("def test_x(): pass\n")
    code, out = run_cli(tmp_path, ["check", "--bank", f"{bank.spec_hash}:{bank.seed}", "--workspace", str(tmp_path / "ws"),
                                   "--implementer-model", "m", "--implementer-family", "google", "--json"], c)
    assert code == FAILED and json.loads(out.split("\n::error")[0])["status"] == "Rejected: tests tampered"


@pytest.mark.parametrize("argv", [[], ["nope"], ["check"], ["spec"], ["bank", "--spec", "x"]])
def test_cli_usage_errors_return_2(tmp_path, argv):
    assert run_cli(tmp_path, argv)[0] == USAGE


def test_cli_missing_and_corrupt_inputs_fail_cleanly(tmp_path):
    code, out = run_cli(tmp_path, ["spec", "--text", str(tmp_path / "nope.txt")])
    assert code == USAGE and "error" in out
    (tmp_path / "bad.json").write_text("{not json")
    assert run_cli(tmp_path, ["bank", "--spec", str(tmp_path / "bad.json"), "--workspace", str(tmp_path / "w")])[0] == USAGE
    code, out = run_cli(tmp_path, ["check", "--bank", "missing:0", "--implementer-model", "m", "--implementer-family", "g"])
    assert code == USAGE and "missing" in out


def test_cli_incomplete_bank_exit_code(tmp_path):
    writer = ScriptedProvider("p", [json.dumps({"tests": [{"name": "a", "code": "def test_a(): pass", "requirement_ids": ["R1"]}]})] * 10)
    c = Context(env={}, repo=JsonRepository(tmp_path / "db"), verifier=FallbackChain([writer]),
                long_context=FallbackChain([ScriptedProvider("s")]), sandbox=FakeSandbox())
    (tmp_path / "spec.json").write_text(spec_obj().model_dump_json())
    code, out = run_cli(tmp_path, ["bank", "--spec", str(tmp_path / "spec.json"), "--workspace", str(tmp_path / "ws")], c)
    assert code == INCOMPLETE and "requirements without tests" in out


# ---- repo ingestion hygiene
def test_load_codebase_skips_secrets_binaries_vendor_and_symlinks(tmp_path):
    (tmp_path / "app.py").write_text("print(1)")
    (tmp_path / ".env").write_text("API_KEY=sk-real")
    (tmp_path / ".env.example").write_text("API_KEY=")
    (tmp_path / "img.png").write_bytes(b"\x89PNG\xff\xfe")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules/x.js").write_text("x")
    (tmp_path / "big.txt").write_text("a" * 300_000)
    (tmp_path / "link").symlink_to("/etc/hosts")
    files = load_codebase(tmp_path)
    assert set(files) == {"app.py", ".env.example"}
    assert "sk-real" not in json.dumps(files)
