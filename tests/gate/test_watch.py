import json
from io import StringIO
from pathlib import Path

import pytest

from sharley.gate.cli import FAILED, OK, main
from sharley.gate.context import Context
from sharley.gate.git import SHA, GhHost, GitHost, MergedChange
from sharley.gate.service import make_bank, publish_examples
from sharley.gate.watch import watch_once
from sharley.harness import FallbackChain
from sharley.runner.base import RunReport, Sandbox, TestResult
from sharley.schemas import ModelRef
from sharley.storage import JsonRepository
from tests.fakes import EchoWriter, ScriptedProvider
from tests.gate.test_gate import FakeSandbox, spec_obj

IMPL = ModelRef(provider="external", model="argon", family="google")
S1, S2, S3 = "a" * 40, "b" * 40, "c" * 40


class FakeHost(GitHost):
    def __init__(self, trees, changes):
        self.trees, self.changes, self.reverts, self.polls = trees, changes, [], []

    def merged_since(self, last):
        self.polls.append(last)
        shas = [c.sha for c in self.changes]
        return self.changes[shas.index(last) + 1:] if last in shas else list(self.changes)

    def checkout(self, sha):
        return self.trees[sha]

    def open_revert_pr(self, change, reason):
        self.reverts.append((change, reason))
        return f"https://github.com/o/r/pull/{900 + change.pr}"


class SwitchSandbox(Sandbox):
    """Passes for trees named good-*, fails (boot) for others."""
    name = "switch"

    def health(self):
        return True

    def run(self, workspace, tests, stack, *, timeout_s=180):
        if "good" in str(workspace):
            return RunReport(results=[TestResult(test_id=t.id, passed=True, kind="pass") for t in tests])
        return RunReport(boot_ok=False, build_output="regression")


@pytest.fixture
def world(tmp_path):
    repo = JsonRepository(tmp_path / "db")
    chain = FallbackChain([EchoWriter()])
    bank = make_bank(spec_obj(), repo, chain)
    trees = {}
    for sha, kind in ((S1, "good-1"), (S2, "bad-2"), (S3, "bad-3")):
        t = tmp_path / kind / "tree"
        publish_examples(bank, spec_obj(), t)
        trees[sha] = t
    return repo, bank, trees


def run(world, changes, **kw):
    repo, bank, trees = world
    host = FakeHost(trees, changes)
    res = watch_once(host=host, bank=bank, sandbox=SwitchSandbox(), stack="docker-api", implementer=IMPL, repo=repo, **kw)
    return host, res


def test_passing_merge_opens_no_revert(world):
    host, res = run(world, [MergedChange(1, S1)])
    assert [r.status for r in res] == ["Accepted"] and host.reverts == []


def test_failing_merge_opens_revert_pr_with_plain_english_reason(world):
    host, res = run(world, [MergedChange(2, S2)])
    assert res[0].status == "Build Failed" and res[0].revert_url.endswith("/902")
    change, reason = host.reverts[0]
    assert change.pr == 2 and "Build Failed" in reason


def test_state_prevents_rejudging_and_double_reverts(world):
    changes = [MergedChange(1, S1), MergedChange(2, S2)]
    host, res = run(world, changes)
    assert [r.status for r in res] == ["Accepted", "Build Failed"]
    host2, res2 = run(world, changes)
    assert res2 == [] and host2.polls == [S2] and host2.reverts == []


def test_each_failing_merge_gets_its_own_revert(world):
    host, res = run(world, [MergedChange(2, S2), MergedChange(3, S3)])
    assert [c.pr for c, _ in host.reverts] == [2, 3]


def test_worktrees_are_cleaned_up(world):
    repo, bank, trees = world
    run(world, [MergedChange(1, S1)])
    assert not trees[S1].parent.exists()


# ---- GhHost with a recording command runner
class Cmds:
    def __init__(self, listing=None, fail_on=None):
        self.calls, self.listing, self.fail_on = [], listing or [], fail_on

    def __call__(self, argv, cwd):
        self.calls.append(argv)
        if self.fail_on and self.fail_on in argv:
            return 1, "boom"
        if argv[:3] == ["gh", "pr", "list"]:
            return 0, json.dumps(self.listing)
        if argv[:3] == ["gh", "pr", "create"]:
            return 0, "https://github.com/o/r/pull/77\n"
        return 0, ""


LISTING = [{"number": 2, "mergedAt": "2026-01-02", "mergeCommit": {"oid": S2}},
           {"number": 1, "mergedAt": "2026-01-01", "mergeCommit": {"oid": S1}},
           {"number": 3, "mergedAt": "2026-01-03", "mergeCommit": {"oid": S3}}]


def test_ghhost_orders_oldest_first_and_slices_after_last():
    host = GhHost(Path("."), cmd=Cmds(LISTING))
    assert [c.pr for c in host.merged_since(S1)] == [2, 3]
    assert [c.pr for c in host.merged_since(S3)] == []
    assert [c.pr for c in host.merged_since(None)] == [3]  # first run never replays history
    assert [c.pr for c in host.merged_since("f" * 40)] == [3]


def test_ghhost_revert_flow_commands():
    cmds = Cmds()
    url = GhHost(Path("."), cmd=cmds).open_revert_pr(MergedChange(5, S2), "why")
    flat = [" ".join(c) for c in cmds.calls]
    assert any(c.startswith("git revert -m 1 --no-edit " + S2) for c in flat)
    assert any("git push -u origin sharley/revert-pr-5" in c for c in flat) and url.endswith("/77")
    assert not any("--force" in c or "merge" in c.split() for c in flat)  # never force-push or auto-merge


@pytest.mark.parametrize("sha", ["--upload-pack=evil", "abc", "A" * 40, "a" * 39 + ";", ""])
def test_ghhost_refuses_non_sha_input(sha):
    host = GhHost(Path("."), cmd=Cmds())
    with pytest.raises(ValueError):
        host.checkout(sha)
    with pytest.raises(ValueError):
        host.open_revert_pr(MergedChange(1, sha), "x")


def test_ghhost_rejects_bad_pr_numbers_and_surfaces_command_failures():
    with pytest.raises(ValueError):
        GhHost(Path("."), cmd=Cmds()).open_revert_pr(MergedChange(0, S1), "x")
    with pytest.raises(RuntimeError, match="boom"):
        GhHost(Path("."), cmd=Cmds(fail_on="push")).open_revert_pr(MergedChange(1, S1), "x")


def test_sha_pattern():
    assert SHA.match("0123456789abcdef" * 2 + "01234567") and not SHA.match("xyz")


# ---- CLI wiring
def test_cli_watch_once(world, tmp_path):
    repo, bank, trees = world
    (tmp_path / "bank.json").write_text(bank.model_dump_json())
    ctx = Context(env={}, repo=repo, verifier=FallbackChain([ScriptedProvider("p")]),
                  long_context=FallbackChain([ScriptedProvider("s")]), sandbox=SwitchSandbox())
    out = StringIO()
    from sharley.gate import cli
    host = FakeHost(trees, [MergedChange(1, S1), MergedChange(2, S2)])
    a = cli.build_parser().parse_args(["watch", "--bank-file", str(tmp_path / "bank.json"), "--implementer-model", "m",
                                       "--implementer-family", "google"])
    assert cli.cmd_watch(a, ctx, out, host=host) == OK
    text = out.getvalue()
    assert "PR #1" in text and "Accepted" in text and "PR #2" in text and "revert https://github.com/o/r/pull/902" in text


def test_workflow_file_is_inert_without_secret_and_leaks_nothing():
    wf = (Path(__file__).resolve().parents[2] / ".github/workflows/sharley.yml").read_text()
    assert "steps.armed.outputs.yes == 'true'" in wf and "secrets.SHARLEY_BANK_JSON" in wf
    assert wf.count("if: steps.armed") >= 3 and "echo \"$SHARLEY_BANK_JSON\"" not in wf  # never echo the sealed bank
