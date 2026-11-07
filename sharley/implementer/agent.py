"""The coding agent being judged. It sees the task and the EXAMPLE tests only; never the sealed bank."""
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from sharley.harness import FallbackChain, Step
from sharley.profiles import PROFILES
from sharley.runner.base import Sandbox
from sharley.schemas import TestBank
from sharley.schemas.spec import StackName

MAX_FILES = 60
MAX_FILE_CHARS = 100_000
ROUNDS = 3
PROTECTED = {".env", "sharley.yaml", "SHARLEY.md"}


class FileOut(BaseModel):
    path: str
    content: str


class ImplIn(BaseModel):
    task: str
    contract: str
    example_tests: list[dict[str, str]]
    failing: list[dict[str, str]] = Field(default_factory=list)
    existing_files: list[str] = Field(default_factory=list)


class ImplOut(BaseModel):
    files: list[FileOut] = Field(min_length=1)


IMPLEMENT = Step("implement", "You are a software engineer. Implement the application described in `task`, following "
                 "`contract` (layout, run command, health check). Make every example test pass. Return COMPLETE file "
                 "contents for every file you create or change. Use only libraries available offline: python 3.12 "
                 "stdlib, fastapi, uvicorn, httpx, pydantic.", ImplIn, ImplOut, tier="strong")


@dataclass
class ImplementResult:
    rounds: int
    example_passed: int
    example_total: int
    written: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


def safe_target(workspace: Path, rel: str, test_dir: str) -> Path | None:
    """Resolve a model-chosen path inside the workspace, or None if it must be refused."""
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts or not rel.strip() or p.name in PROTECTED or p.name.startswith(".env"):
        return None
    if p.parts and p.parts[0] == test_dir:
        return None  # the implementer may not touch the tests
    target = (workspace / p).resolve()
    return target if target.is_relative_to(workspace.resolve()) else None


def implement(chain: FallbackChain, bank: TestBank, workspace: Path, sandbox: Sandbox, stack: StackName, task: str,
              rounds: int = ROUNDS) -> ImplementResult:
    test_dir = PROFILES[stack].test_dir
    contract = (workspace / "sharley.yaml").read_text() if (workspace / "sharley.yaml").exists() else ""
    examples = bank.examples
    result = ImplementResult(0, 0, len(examples))
    failing: list[dict[str, str]] = []
    for n in range(1, rounds + 1):
        existing = sorted(p.relative_to(workspace).as_posix() for p in workspace.rglob("*")
                          if p.is_file() and test_dir not in p.relative_to(workspace).parts[:1])
        out = IMPLEMENT.run(chain, ImplIn(task=task, contract=contract, failing=failing, existing_files=existing,
                                          example_tests=[{"file": t.file, "code": t.code} for t in examples]))
        for f in out.files[:MAX_FILES]:
            target = safe_target(workspace, f.path, test_dir)
            if target is None or len(f.content) > MAX_FILE_CHARS:
                result.rejected.append(f.path)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f.content)
            result.written.append(f.path)
        report = sandbox.run(workspace, examples, stack, timeout_s=180)
        by_id = {r.test_id: r for r in report.results}
        result.rounds = n
        result.example_passed = sum(by_id[t.id].passed for t in examples if t.id in by_id)
        if report.boot_ok and result.example_passed == len(examples):
            break
        failing = ([{"test": t.file, "error": by_id[t.id].output[:400]} for t in examples
                    if t.id in by_id and not by_id[t.id].passed] or [{"test": "boot", "error": report.build_output[-400:]}])
    return result
