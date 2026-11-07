"""Intentionally flawed sample backends and their fixed twins (ground truth for detection and false-failure checks)."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "sample-backends"
NAMES = ("payments", "electricity")
IGNORE = shutil.ignore_patterns("__pycache__", "tests", "*.md")


def backend_dir(name: str) -> Path:
    if name not in NAMES:
        raise KeyError(name)
    return ROOT / name


def spec_text(name: str) -> str:
    return (backend_dir(name) / "SPEC.md").read_text()


def flaws(name: str) -> list[dict]:
    return json.loads((backend_dir(name) / "flaws.json").read_text())


def flaw_ids(name: str) -> list[str]:
    return sorted({f["id"] for f in flaws(name)})


def fixed_copy(name: str, dest: Path) -> Path:
    """Copy the app and apply every flaw's line edit. Fails loudly if an edit no longer matches exactly once."""
    shutil.copytree(backend_dir(name), dest, ignore=IGNORE)
    for f in flaws(name):
        path = dest / f["file"]
        text = path.read_text()
        if text.count(f["flawed"]) != 1:
            raise ValueError(f"{f['id']}: flawed line not found exactly once in {f['file']}")
        path.write_text(text.replace(f["flawed"], f["fixed"]))
    return dest


def flawed_copy(name: str, dest: Path) -> Path:
    shutil.copytree(backend_dir(name), dest, ignore=IGNORE)
    return dest
