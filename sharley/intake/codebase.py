"""Deterministic codebase parsing: routes, functions, schemas, env refs, Dockerfiles."""
import re

from pydantic import Field

from sharley.profiles import detect_stack
from sharley.schemas.spec import StackName, Strict

_ENV = re.compile(
    r"process\.env\.([A-Z_][A-Z0-9_]*)|process\.env\[['\"]([A-Z_][A-Z0-9_]*)['\"]\]"
    r"|os\.environ\[['\"]([A-Z_][A-Z0-9_]*)['\"]\]|os\.environ\.get\(['\"]([A-Z_][A-Z0-9_]*)['\"]"
    r"|os\.getenv\(['\"]([A-Z_][A-Z0-9_]*)['\"]")
_PY_ROUTE = re.compile(r"@\w+\.(get|post|put|patch|delete|route)\(\s*['\"]([^'\"]+)['\"](?:.*methods=\[([^\]]*)\])?")
_NEXT_ROUTE = re.compile(r"^(?:src/)?(?:app|pages)/(.*?)(?:/route|/index)?\.(?:ts|js|tsx|jsx)$")
_NEXT_METHOD = re.compile(r"export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE)\b")
_FUNC = re.compile(r"^\s*(?:async\s+)?(?:def|function)\s+([A-Za-z_]\w*)", re.M)
_SCHEMA = re.compile(r"^class\s+(\w+)\((?:\w+\.)?(?:BaseModel|Base|Model)\)|CREATE TABLE\s+(?:IF NOT EXISTS\s+)?(\w+)|^model\s+(\w+)\s*\{",
                     re.M | re.I)
MAX_ITEMS = 150  # keeps a 15k-LOC repo summary to a few KB
_DOCKER = re.compile(r"^\s*(FROM|EXPOSE|ENV|ARG|CMD|ENTRYPOINT)\s+(.+)$", re.M)


class CodebaseSummary(Strict):
    stack: StackName | None
    routes: list[str] = Field(default_factory=list)
    functions: list[str] = Field(default_factory=list)
    schemas: list[str] = Field(default_factory=list)
    env_vars: list[str] = Field(default_factory=list)
    dockerfile: list[str] = Field(default_factory=list)


def env_refs(files: dict[str, str]) -> dict[str, list[str]]:
    """{ENV_VAR: [files that reference it]} across all non-Dockerfile sources."""
    out: dict[str, set[str]] = {}
    for path, text in files.items():
        for m in _ENV.finditer(text):
            out.setdefault(next(g for g in m.groups() if g), set()).add(path)
    return {k: sorted(v) for k, v in sorted(out.items())}


def summarize_codebase(files: dict[str, str]) -> CodebaseSummary:
    routes, funcs, schemas, docker = set(), set(), set(), []
    for path, text in files.items():
        for m in _PY_ROUTE.finditer(text):
            verb = m.group(1).upper() if m.group(1) != "route" else (m.group(3) or "GET").replace("'", "").replace('"', "").replace(" ", "")
            routes.add(f"{verb} {m.group(2)}")
        nm = _NEXT_ROUTE.match(path)
        if nm and ("route." in path or "pages/api" in path):
            base = "/" + nm.group(1).replace("[", ":").replace("]", "")
            for verb in _NEXT_METHOD.findall(text) or (["ANY"] if "pages/api" in path else []):
                routes.add(f"{verb} {base if base.startswith('/api') or 'pages/api' not in path else base.replace('/pages', '')}")
        funcs.update(_FUNC.findall(text))
        for m in _SCHEMA.finditer(text):
            schemas.add(next(g for g in m.groups() if g))
        if path.split("/")[-1].startswith("Dockerfile"):
            docker += [f"{k} {v.strip()}" for k, v in _DOCKER.findall(text)]
    return CodebaseSummary(stack=detect_stack(files), routes=sorted(routes), functions=sorted(funcs),
                           schemas=sorted(schemas), env_vars=sorted(env_refs(files)), dockerfile=docker)


def render_summary(s: CodebaseSummary) -> str:
    lines = [f"Stack: {s.stack or 'unknown'}"]
    for title, items in (("Routes", s.routes), ("Functions", s.functions), ("Schemas", s.schemas),
                         ("Environment variables", s.env_vars), ("Dockerfile", s.dockerfile)):
        if items:
            lines.append(f"{title}:")
            lines += [f"- {i}" for i in items[:MAX_ITEMS]]
            if len(items) > MAX_ITEMS:
                lines.append(f"- ... and {len(items) - MAX_ITEMS} more")
    return "\n".join(lines)
