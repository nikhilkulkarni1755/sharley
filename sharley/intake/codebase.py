"""Deterministic codebase parsing: routes, functions, schemas, env refs, Dockerfiles."""
import json
import re

import yaml
from pydantic import Field

from sharley.profiles import detect_stack
from sharley.schemas.spec import StackName, Strict

_ENV = re.compile(
    r"process\.env\.([A-Z_][A-Z0-9_]*)|process\.env\[['\"]([A-Z_][A-Z0-9_]*)['\"]\]"
    r"|os\.environ\[['\"]([A-Z_][A-Z0-9_]*)['\"]\]|os\.environ\.get\(['\"]([A-Z_][A-Z0-9_]*)['\"]"
    r"|os\.getenv\(['\"]([A-Z_][A-Z0-9_]*)['\"]"
    r"|\bconfig\(\s*['\"]([A-Z_][A-Z0-9_]*)['\"]")
_PY_ROUTE = re.compile(r"@\w+\.(get|post|put|patch|delete|route)\(\s*['\"]([^'\"]*)['\"](?:.*methods=\[([^\]]*)\])?")
_NEXT_ROUTE = re.compile(r"^(?:src/)?(?:app|pages)/(.*?)(?:/route|/index)?\.(?:ts|js|tsx|jsx)$")
_NEXT_METHOD = re.compile(r"export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE)\b")
_FUNC = re.compile(r"^\s*(?:async\s+)?(?:def|function)\s+([A-Za-z_]\w*)", re.M)
_SCHEMA = re.compile(r"^class\s+(\w+)\([^)]*\b(?:BaseModel|SQLModel|Base|Model|DeclarativeBase|Document)\b[^)]*\)|^class\s+(\w+)\([^)]*table\s*=\s*True[^)]*\)|CREATE TABLE\s+(?:IF NOT EXISTS\s+)?(\w+)|^model\s+(\w+)\s*\{",
                     re.M | re.I)
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|e2e|playwright|migrations)(/|$)|(^|/)(test_[^/]*|conftest\.py)$|\.(test|spec)\.[jt]sx?$|playwright\.config")
OPENAPI = re.compile(r"(^|/)(openapi|swagger)[^/]*\.(ya?ml|json)$", re.I)
_ROUTER_PREFIX = re.compile(r"APIRouter\([^)]*?prefix\s*=\s*['\"]([^'\"]*)['\"]")
_INCLUDE = re.compile(r"include_router\(([^()]*)\)")
_PREFIX_ARG = re.compile(r"prefix\s*=\s*['\"]([^'\"]*)['\"]")
_SETTINGS_CLASS = re.compile(r"^class\s+\w+\([^)]*Settings[^)]*\):\n((?:[ \t]+.*\n|\n)+)", re.M)
_FIELD = re.compile(r"^[ \t]{4}([A-Za-z_][A-Za-z0-9_]*)\s*[:=]", re.M)
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
    """{ENV_VAR: [files that reference it]}; test files are ignored and pydantic Settings fields are included."""
    out: dict[str, set[str]] = {}
    for path, text in files.items():
        if TEST_PATH.search(path):
            continue
        for m in _ENV.finditer(text):
            out.setdefault(next(g for g in m.groups() if g), set()).add(path)
        for block in _SETTINGS_CLASS.findall(text):
            for name in _FIELD.findall(block):
                if name != "model_config" and not name.startswith("_"):
                    out.setdefault(name.upper(), set()).add(path)
    return {k: sorted(v) for k, v in sorted(out.items())}


def openapi_routes(files: dict[str, str]) -> set[str]:
    routes = set()
    for path, text in files.items():
        if not OPENAPI.search(path):
            continue
        try:
            doc = json.loads(text) if path.endswith(".json") else yaml.safe_load(text)
        except (ValueError, yaml.YAMLError):
            continue
        for route, ops in ((doc or {}).get("paths") or {}).items():
            for verb in (ops or {}) if isinstance(ops, dict) else []:
                if verb.lower() in {"get", "post", "put", "patch", "delete"}:
                    routes.add(f"{verb.upper()} {route}")
    return routes


def router_prefixes(files: dict[str, str]) -> dict[str, str]:
    """{module basename: full URL prefix} from APIRouter(prefix=...) and (nested) include_router(..., prefix=...)."""
    own, edges = {}, []
    for path, text in files.items():
        if not path.endswith(".py") or TEST_PATH.search(path):
            continue
        base = path.rsplit("/", 1)[-1][:-3]
        if m := _ROUTER_PREFIX.search(text):
            own[base] = m.group(1)
        for m in _INCLUDE.finditer(text):
            args = m.group(1)
            child = args.split(",")[0].strip().removesuffix(".router").split(".")[-1]
            if child:
                edges.append((base, child, (_PREFIX_ARG.search(args) or [None, ""])[1]))

    def resolve(mod: str, depth: int = 0) -> str:
        if depth > 5:
            return ""
        parents = [(p, pre) for p, c, pre in edges if c == mod and p != mod]
        up = resolve(parents[0][0], depth + 1) + parents[0][1] if parents else ""
        return up + own.get(mod, "")

    return {mod: resolve(mod) for mod in {*own, *(c for _, c, _ in edges)}}


def summarize_codebase(files: dict[str, str]) -> CodebaseSummary:
    routes, funcs, schemas, docker = openapi_routes(files), set(), set(), []
    prefixes = router_prefixes(files)
    for path, text in files.items():
        is_test = bool(TEST_PATH.search(path))
        if not is_test:
            prefix = prefixes.get(path.rsplit("/", 1)[-1].rsplit(".", 1)[0], "") if path.endswith(".py") else ""
            for m in _PY_ROUTE.finditer(text):
                verb = m.group(1).upper() if m.group(1) != "route" else (m.group(3) or "GET").replace("'", "").replace('"', "").replace(" ", "")
                full = m.group(2) if m.group(2).startswith(prefix) and prefix else prefix + m.group(2)
                routes.add(f"{verb} {full or '/'}")
            nm = _NEXT_ROUTE.match(path)
            if nm and ("route." in path or "pages/api" in path):
                base = "/" + nm.group(1).replace("[", ":").replace("]", "")
                for verb in _NEXT_METHOD.findall(text) or (["ANY"] if "pages/api" in path else []):
                    routes.add(f"{verb} {base if base.startswith('/api') or 'pages/api' not in path else base.replace('/pages', '')}")
            if not path.endswith((".tsx", ".jsx")):  # React components are UI, not API surface
                funcs.update(_FUNC.findall(text))
        for m in _SCHEMA.finditer(text):
            if not is_test:
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
