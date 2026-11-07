"""Use-case functions behind the CLI, the web API and the Fetch.ai agents."""
from pathlib import Path

from sharley.harness import FallbackChain
from sharley.judge import export_workspace, judge, save_bank, split_bank
from sharley.planner import TraceReport, generate_test_cases
from sharley.profiles import build_contract
from sharley.runner.base import Sandbox
from sharley.schemas import ModelRef, Spec, TestBank, Verdict
from sharley.schemas.spec import StackName
from sharley.storage.repository import Repository


class IncompleteBank(RuntimeError):
    def __init__(self, report: TraceReport):
        super().__init__(f"requirements without tests: {report.uncovered}; unknown refs: {report.unknown_refs}")
        self.report = report


def make_bank(spec: Spec, repo: Repository, chain: FallbackChain, *, stack: StackName | None = None,
              files: dict[str, str] | None = None, rules: list[str] | None = None, seed: int = 0,
              workers: int = 4, allow_partial: bool = False) -> TestBank:
    tests, report = generate_test_cases(spec, repo, chain, stack=stack, files=files, rules=rules, workers=workers)
    if not report.ok and not allow_partial:
        raise IncompleteBank(report)
    bank = split_bank(tests, spec.spec_hash, seed).model_copy(update={"author": chain.active_ref()})
    save_bank(repo, bank)
    return bank


def publish_examples(bank: TestBank, spec: Spec, dest: Path, stack: StackName | None = None) -> list[str]:
    """Give the implementer its workspace: example tests + sharley.yaml contract. Nothing sealed."""
    stack = stack or spec.stack
    contract = build_contract(stack) if stack else None
    return export_workspace(bank, dest, contract)


def check_submission(bank: TestBank, workspace: Path, sandbox: Sandbox, stack: StackName, implementer: ModelRef,
                     repo: Repository | None = None, timeout_s: int = 180) -> Verdict:
    if bank.author is None:
        raise ValueError("bank has no recorded verifier model; regenerate it with `sharley bank`")
    return judge(bank=bank, workspace=workspace, sandbox=sandbox, stack=stack, implementer=implementer,
                 verifier=bank.author, repo=repo, timeout_s=timeout_s)
