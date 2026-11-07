"""The two supported stack profiles, plus deterministic detection and the greenfield contract."""
import json
import re

import yaml
from pydantic import BaseModel

from sharley.schemas.spec import StackName, Strict


class Profile(Strict):
    name: StackName
    test_frameworks: list[str]
    test_dir: str
    test_ext: str
    boot_cmd: str
    health_path: str
    test_cmds: list[str]
    port: int


PROFILES: dict[str, Profile] = {
    "nextjs": Profile(name="nextjs", test_frameworks=["vitest", "playwright"], test_dir="tests",
                      test_ext=".test.ts", boot_cmd="npm run build && npm start", health_path="/api/health",
                      test_cmds=["npx vitest run", "npx playwright test"], port=3000),
    "docker-api": Profile(name="docker-api", test_frameworks=["pytest"], test_dir="tests",
                          test_ext=".py", boot_cmd="docker build -t app . && docker run -p 8000:8000 app",
                          health_path="/health", test_cmds=["pytest -q tests"], port=8000),
}

_PY_WEB = re.compile(r"^\s*(fastapi|flask|django|starlette|aiohttp)\b", re.I | re.M)


def detect_stack(files: dict[str, str]) -> StackName | None:
    """Plain-code stack detection from {path: content}."""
    pkg = files.get("package.json")
    if pkg:
        try:
            data = json.loads(pkg)
        except ValueError:
            data = {}
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        if "next" in deps:
            return "nextjs"
    py_deps = "\n".join(files.get(f, "") for f in ("requirements.txt", "pyproject.toml"))
    if "Dockerfile" in files and _PY_WEB.search(py_deps):
        return "docker-api"
    return None


class Contract(BaseModel):
    stack: StackName
    layout: dict[str, str]
    run: str
    test: list[str]
    health: str
    required_env: list[str]


def build_contract(stack: StackName, required_env: list[str] | None = None) -> str:
    """sharley.yaml the implementer must build into when no codebase exists."""
    p = PROFILES[stack]
    c = Contract(stack=stack, layout={"tests": p.test_dir, "app": "src" if stack == "nextjs" else "app"},
                 run=p.boot_cmd, test=p.test_cmds, health=f"http://localhost:{p.port}{p.health_path}",
                 required_env=sorted(set(required_env or [])))
    return yaml.safe_dump(c.model_dump(), sort_keys=True)
