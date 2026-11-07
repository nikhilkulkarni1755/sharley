"""sharley watch: judge merged changes; if one fails the sealed tests, open a revert PR."""
import shutil
from dataclasses import dataclass
from pathlib import Path

from sharley.gate.git import GitHost, MergedChange
from sharley.gate.report import render
from sharley.gate.service import check_submission
from sharley.runner.base import Sandbox
from sharley.schemas import ModelRef, TestBank
from sharley.schemas.spec import StackName
from sharley.storage.repository import Repository


@dataclass
class WatchResult:
    change: MergedChange
    status: str
    revert_url: str | None = None


def _state_key(name: str) -> str:
    return f"watch:{name}"


def watch_once(*, host: GitHost, bank: TestBank, sandbox: Sandbox, stack: StackName, implementer: ModelRef,
               repo: Repository, name: str = "default", timeout_s: int = 180) -> list[WatchResult]:
    state = repo.get("runs", _state_key(name)) or {}
    results = []
    for change in host.merged_since(state.get("last_sha")):
        tree = host.checkout(change.sha)
        try:
            verdict = check_submission(bank, tree, sandbox, stack, implementer, timeout_s=timeout_s)
        finally:
            shutil.rmtree(tree.parent, ignore_errors=True)
        url = None
        if verdict.status != "Accepted" and change.sha not in state.get("reverted", []):
            url = host.open_revert_pr(change, render(verdict))
            state["reverted"] = [*state.get("reverted", []), change.sha]
        state["last_sha"] = change.sha
        repo.put("runs", _state_key(name), state)  # persist per change so a crash never re-reverts
        results.append(WatchResult(change, verdict.status, url))
    return results
