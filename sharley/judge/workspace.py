"""What the implementer sees, and the checks that keep it honest."""
import re
from pathlib import Path

from sharley.hashing import sha256_text
from sharley.schemas import TestBank

SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".next"}
CONFIGS = {"conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "sitecustomize.py"}
_SUSPECT = re.compile(r"skip|xfail|deselect|collect_ignore|--ignore|pytest_collection_modifyitems|addopts", re.I)
BRIEF = ("# Sharley\n\nMake the tests in this workspace pass. Sharley will judge your work against additional "
         "hidden tests that you cannot see. Do not edit, skip or delete the provided tests.\n")


class LeakError(RuntimeError):
    pass


def _files(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and not p.is_symlink() and not (set(p.relative_to(root).parts) & SKIP_DIRS):
            yield p


def find_leaks(workspace: Path, bank: TestBank) -> list[str]:
    """Sealed test ids whose file path or code appears anywhere in the workspace."""
    example_code = {t.code.strip() for t in bank.examples}
    sealed = [t for t in bank.sealed if t.code.strip() not in example_code]
    leaks: set[str] = set()
    for p in _files(workspace):
        rel = p.relative_to(workspace).as_posix()
        text = p.read_text(errors="ignore") if p.stat().st_size < 1_000_000 else ""
        for t in sealed:
            if rel == t.file or t.code.strip() in text:
                leaks.add(t.id)
    return sorted(leaks)


def export_workspace(bank: TestBank, dest: Path, contract_yaml: str | None = None) -> list[str]:
    """Write ONLY example tests (+ contract + brief). Refuses to finish if anything sealed leaked."""
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for t in bank.examples:
        p = dest / t.file
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(t.code)
        written.append(t.file)
    if contract_yaml:
        (dest / "sharley.yaml").write_text(contract_yaml)
    (dest / "SHARLEY.md").write_text(BRIEF)
    if leaks := find_leaks(dest, bank):
        raise LeakError(f"sealed tests leaked into workspace: {leaks}")
    return written


def check_tamper(workspace: Path, bank: TestBank) -> list[str]:
    """Plain-English issues if any provided test was edited, deleted, or neutralised by config."""
    issues = []
    for t in bank.examples:
        p = workspace / t.file
        if not p.is_file():
            issues.append(f"provided test {t.file} was deleted")
        elif sha256_text(p.read_text(errors="ignore")) != t.sha256:
            issues.append(f"provided test {t.file} was edited")
    for p in _files(workspace):
        if p.name in CONFIGS and _SUSPECT.search(p.read_text(errors="ignore")):
            issues.append(f"{p.relative_to(workspace).as_posix()} tries to skip or filter tests")
    return issues
