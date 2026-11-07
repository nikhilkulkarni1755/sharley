"""Deterministic env checks: code references vs .env.example vs deploy config; boot + health."""
import json
import re

from pydantic import BaseModel

from sharley.generator.writer import DraftTest
from sharley.intake.codebase import env_refs
from sharley.profiles import PROFILES
from sharley.schemas.spec import StackName

_TOKEN = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
_DEPLOY = re.compile(r"(^|/)(Dockerfile[^/]*|docker-compose[^/]*\.ya?ml|vercel\.json|wrangler\.toml|render\.yaml|fly\.toml)$")
# Dockerfile instructions that look like env names but are not
_NOISE = {"FROM", "RUN", "CMD", "COPY", "ADD", "ENV", "ARG", "EXPOSE", "WORKDIR", "ENTRYPOINT", "USER", "AS", "TRUE", "FALSE"}


class EnvReport(BaseModel):
    referenced: list[str]
    missing_from_example: list[str]
    undeclared_in_deploy: list[str]


def example_vars(files: dict[str, str]) -> set[str]:
    text = files.get(".env.example", "")
    return {m.group(1) for m in re.finditer(r"^\s*([A-Z_][A-Z0-9_]*)\s*=", text, re.M)}


def deploy_vars(files: dict[str, str]) -> set[str]:
    found: set[str] = set()
    for path, text in files.items():
        if _DEPLOY.search(path):
            found |= set(_TOKEN.findall(text)) - _NOISE
    return found


def check_env(files: dict[str, str]) -> EnvReport:
    ref = set(env_refs(files))
    return EnvReport(referenced=sorted(ref), missing_from_example=sorted(ref - example_vars(files)),
                     undeclared_in_deploy=sorted(ref - deploy_vars(files)))


_PY_HEAD = '''import os
import pathlib

import httpx
'''
_PY_ENV = '''

def test_env_example_declares_every_referenced_variable():
    declared = {{l.split("=")[0].strip() for l in pathlib.Path(".env.example").read_text().splitlines() if "=" in l}}
    assert not set({vars}) - declared
'''
_PY = '''

def test_app_boots_and_health_returns_200():
    base = os.environ.get("BASE_URL", "http://localhost:{port}")
    assert httpx.get(base + "{health}", timeout=10).status_code == 200
'''
_TS = '''import {{ readFileSync }} from "node:fs";
import {{ expect, test }} from "vitest";

test("env example declares every referenced variable", () => {{
  const declared = readFileSync(".env.example", "utf8").split("\\n").map((l) => l.split("=")[0].trim());
  for (const v of {vars}) expect(declared).toContain(v);
}});

test("app boots and health returns 200", async () => {{
  const res = await fetch((process.env.BASE_URL ?? "http://localhost:{port}") + "{health}");
  expect(res.status).toBe(200);
}});
'''


def env_tests(files: dict[str, str], stack: StackName, requirement_ids: list[str]) -> list[DraftTest]:
    """One deterministic test module tagged to the deployment requirements."""
    if not requirement_ids:
        return []
    p = PROFILES[stack]
    vars_ = json.dumps(sorted(env_refs(files)))
    has_example = ".env.example" in files or not files  # greenfield contracts will ship one; an existing repo without it is not tested for it
    tpl = (_PY_HEAD + (_PY_ENV if has_example else "") + _PY) if stack == "docker-api" else _TS
    return [DraftTest(name="env example and boot health", requirement_ids=requirement_ids,
                      code=tpl.format(vars=vars_, port=p.port, health=p.health_path),
                      hint="Environment variables are not all declared, or the app does not boot with a healthy /health.")]
