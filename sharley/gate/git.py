"""GitHub/git operations behind an interface so the watcher is testable without a network."""
import json
import re
import subprocess
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")
Cmd = Callable[[list[str], Path | None], tuple[int, str]]


@dataclass(frozen=True)
class MergedChange:
    pr: int
    sha: str


class GitHost(ABC):
    @abstractmethod
    def merged_since(self, last_sha: str | None) -> list[MergedChange]:
        """Merged PRs after last_sha, oldest first."""

    @abstractmethod
    def checkout(self, sha: str) -> Path: ...

    @abstractmethod
    def open_revert_pr(self, change: MergedChange, reason: str) -> str: ...


def run_cmd(argv: list[str], cwd: Path | None = None) -> tuple[int, str]:
    p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr)


class GhHost(GitHost):
    """Uses the `gh` and `git` CLIs. Only validated PR numbers and SHAs ever reach a command line."""

    def __init__(self, repo_path: Path, base: str = "main", cmd: Cmd = run_cmd):
        self.repo, self.base, self.cmd = repo_path, base, cmd

    def _ok(self, argv: list[str], cwd: Path | None = None) -> str:
        code, out = self.cmd(argv, cwd or self.repo)
        if code != 0:
            raise RuntimeError(f"{' '.join(argv[:3])} failed: {out.strip()[:300]}")
        return out

    def merged_since(self, last_sha):
        raw = json.loads(self._ok(["gh", "pr", "list", "--state", "merged", "--base", self.base, "--limit", "50",
                                   "--json", "number,mergeCommit,mergedAt"]))
        changes = [MergedChange(pr=int(r["number"]), sha=r["mergeCommit"]["oid"])
                   for r in sorted(raw, key=lambda r: r["mergedAt"]) if r.get("mergeCommit")]
        changes = [c for c in changes if SHA.match(c.sha)]
        if last_sha is None:
            return changes[-1:]  # first run: judge only the newest merge, never replay history
        shas = [c.sha for c in changes]
        return changes[shas.index(last_sha) + 1:] if last_sha in shas else changes[-1:]

    def checkout(self, sha):
        if not SHA.match(sha):
            raise ValueError("invalid commit sha")
        dest = Path(tempfile.mkdtemp(prefix="sharley-watch-")) / "tree"
        self._ok(["git", "fetch", "origin", sha])
        self._ok(["git", "worktree", "add", "--detach", str(dest), sha])
        return dest

    def open_revert_pr(self, change, reason):
        if not SHA.match(change.sha) or change.pr < 1:
            raise ValueError("invalid change")
        branch = f"sharley/revert-pr-{change.pr}"
        wt = Path(tempfile.mkdtemp(prefix="sharley-revert-")) / "tree"
        self._ok(["git", "fetch", "origin", self.base])
        self._ok(["git", "worktree", "add", "-b", branch, str(wt), f"origin/{self.base}"])
        self._ok(["git", "revert", "-m", "1", "--no-edit", change.sha], wt)
        self._ok(["git", "push", "-u", "origin", branch], wt)
        body = (f"Sharley's sealed tests failed after PR #{change.pr} merged.\n\n{reason}\n\n"
                "This revert PR was opened automatically; review before merging.")
        return self._ok(["gh", "pr", "create", "--base", self.base, "--head", branch,
                         "--title", f"Revert PR #{change.pr}: failed Sharley sealed tests", "--body", body], wt).strip()
