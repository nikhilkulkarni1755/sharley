"""Enumerate mutants of an app directory, split train/heldout, and apply one to a copy."""
import ast
import shutil
from pathlib import Path

from sharley.hashing import sha256_text
from sharley.mutation.operators import OPERATORS
from sharley.schemas import Mutant

SKIP_LINE = ("#", '"""', "import ", "from ")


def generate_mutants(app_dir: Path, seed: int = 0, heldout_every: tuple[int, ...] = (1, 3)) -> list[Mutant]:
    """~60/40 train/heldout, stratified per operator so each operator is represented in both when possible."""
    found = []
    for path in sorted(app_dir.rglob("*.py")):
        rel = path.relative_to(app_dir).as_posix()
        if rel.endswith("__init__.py") or "/oracle/" in f"/{rel}":
            continue
        source = path.read_text()
        for n, line in enumerate(source.splitlines(), 1):
            if line.strip().startswith(SKIP_LINE):
                continue
            for op in OPERATORS:
                if op.marker and f"mut:{op.marker}" not in line:
                    continue
                new = op.fn(line)
                if new is None or new == line:
                    continue
                mutated_source = "\n".join(source.splitlines()[:n - 1] + [new] + source.splitlines()[n:])
                try:
                    ast.parse(mutated_source)
                except SyntaxError:
                    continue
                found.append((rel, n, op, line, new))
    found.sort(key=lambda t: (t[0], t[1], t[2].name))
    by_op: dict[str, list] = {}
    for item in found:
        by_op.setdefault(item[2].name, []).append(item)
    mutants = []
    groups = [v for v in by_op.values() if len(v) > 1]
    groups.append([item for v in by_op.values() if len(v) == 1 for item in v])  # singleton operators share one pool
    for items in groups:
        ranked = sorted(items, key=lambda t: sha256_text(f"{seed}:{t[0]}:{t[1]}:{t[2].name}"))
        for i, (rel, n, op, line, new) in enumerate(ranked):
            split = "heldout" if i % 5 in heldout_every else "train"
            mutants.append(Mutant(id="", operator=op.name, category=op.category, file=rel, line=n,
                                  original=line, mutated=new, split=split))
    mutants.sort(key=lambda m: (m.file, m.line, m.operator))
    return [m.model_copy(update={"id": f"M{i:03d}"}) for i, m in enumerate(mutants, 1)]


def apply_mutant(app_dir: Path, mutant: Mutant, dest: Path) -> Path:
    """Copy app_dir to dest and rewrite one line. Refuses stale mutants and paths outside the app."""
    target = (app_dir / mutant.file).resolve()
    if not target.is_relative_to(app_dir.resolve()):
        raise ValueError("mutant file escapes the app directory")
    shutil.copytree(app_dir, dest, ignore=shutil.ignore_patterns("__pycache__", "oracle"), symlinks=True)
    out = dest / mutant.file
    lines = out.read_text().splitlines()
    if mutant.line > len(lines) or lines[mutant.line - 1] != mutant.original:
        raise ValueError(f"mutant {mutant.id} is stale: line {mutant.line} no longer matches")
    lines[mutant.line - 1] = mutant.mutated
    out.write_text("\n".join(lines) + "\n")
    return dest
