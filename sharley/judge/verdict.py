"""Run sealed tests in a clean sandbox and return a LeetCode-style verdict."""
import re
import uuid
from pathlib import Path

from sharley.judge.split import ordered_sealed
from sharley.judge.workspace import check_tamper
from sharley.runner.base import Sandbox, TestResult
from sharley.schemas import ModelRef, TestBank, Verdict
from sharley.schemas.spec import StackName
from sharley.storage.repository import Repository

HINT_MAX = 320  # plain-English hints run ~250 chars; cut on a word boundary, never mid-word
_CODEISH = re.compile(r"assert\b|def\s|import\s|==|=>|\(\)|`|\bresp(onse)?\.|\bclient\.", re.I)


class IndependenceError(ValueError):
    pass


def safe_hint(hint: str, requirement_ids: list[str]) -> str:
    """Plain-English only: anything that smells like test code is replaced with a generic line."""
    h = " ".join(hint.split())
    if not h or _CODEISH.search(h):
        return f"behaviour required by {', '.join(requirement_ids)} is not met"
    return h if len(h) <= HINT_MAX else h[:HINT_MAX].rsplit(" ", 1)[0].rstrip(",;:") + "..."


def judge(*, bank: TestBank, workspace: Path, sandbox: Sandbox, stack: StackName, implementer: ModelRef,
          verifier: ModelRef, repo: Repository | None = None, timeout_s: int = 180, run_id: str | None = None) -> Verdict:
    if implementer.family == verifier.family:
        raise IndependenceError(f"implementer and verifier are both {implementer.family!r}; use different model families")
    sealed = ordered_sealed(bank)
    base = dict(total_sealed=len(sealed), implementer=implementer, verifier=verifier, seed=bank.seed,
                spec_hash=bank.spec_hash)

    if issues := check_tamper(workspace, bank):
        verdict = Verdict(status="Rejected: tests tampered", hint="; ".join(issues)[:300], **base)
    else:
        report = sandbox.run(workspace, [*bank.examples, *sealed], stack, timeout_s=timeout_s)
        verdict = _from_report(report, bank, sealed, base)
    if repo is not None:
        repo.put("verdicts", run_id or uuid.uuid4().hex, verdict.model_dump())
    return verdict


def _from_report(report, bank, sealed, base) -> Verdict:
    if not report.boot_ok:
        return Verdict(status="Build Failed", hint=" ".join(report.build_output.split())[-300:], **base)
    if report.timed_out:
        return Verdict(status="Time Limit Exceeded", hint="the app or its tests did not finish in time", **base)
    by_id = {r.test_id: r for r in report.results}
    missing = TestResult(test_id="", passed=False, kind="runtime", output="test did not run")
    example_passed = sum(by_id.get(t.id, missing).passed for t in bank.examples)
    base = {**base, "example_passed": example_passed, "example_total": len(bank.examples)}
    for i, t in enumerate(sealed, 1):
        r = by_id.get(t.id, missing)
        if not r.passed:
            status = "Wrong Answer" if r.kind == "assert" else "Runtime Error"
            return Verdict(status=status, failed_test_index=i, requirement_ids=t.requirement_ids,
                           hint=safe_hint(t.hint, t.requirement_ids), **base)
    return Verdict(status="Accepted", **base)
