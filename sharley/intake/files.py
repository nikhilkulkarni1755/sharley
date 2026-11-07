"""Read a repository directory into {path: text}, skipping binaries, vendored and secret files."""
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".next", "dist", "build", ".sharley"}
MAX_FILE = 200_000
MAX_TOTAL = 5_000_000


def load_codebase(root: Path) -> dict[str, str]:
    files, total = {}, 0
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if not p.is_file() or p.is_symlink() or set(rel.parts) & SKIP_DIRS:
            continue
        if p.name.startswith(".env") and p.name != ".env.example":
            continue  # never ingest real secrets
        if p.stat().st_size > MAX_FILE:
            continue
        try:
            text = p.read_text()
        except UnicodeDecodeError:
            continue
        total += len(text)
        if total > MAX_TOTAL:
            break
        files[rel.as_posix()] = text
    return files
