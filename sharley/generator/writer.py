"""LLM test writing for functional and security families; plain-code validation of every draft."""
import ast

from pydantic import BaseModel, Field

from sharley.harness import FallbackChain, Step
from sharley.profiles import PROFILES
from sharley.schemas.spec import Requirement, StackName
from sharley.schemas.testbank import Family, TestCase


class DraftTest(BaseModel):
    name: str = Field(min_length=1)
    code: str = Field(min_length=1)
    requirement_ids: list[str] = Field(min_length=1)
    hint: str = ""


class WriteIn(BaseModel):
    family: Family
    stack: StackName
    requirements: list[dict[str, str]]
    rules: list[str] = Field(default_factory=list)
    conventions: str
    surface: str = ""  # the app's real routes/schemas/env (existing codebases); empty for greenfield specs


class WriteOut(BaseModel):
    tests: list[DraftTest] = Field(min_length=1)


_COMMON = ("Write runnable tests for ONLY the given requirements. Each test cites the requirement ids it covers "
           "and carries a plain-English hint describing the failure WITHOUT showing test code. Tests must hit the "
           "running app over HTTP (BASE_URL) and be independent of one another. Follow the skill rules strictly. "
           "When `surface` is non-empty it lists the application's REAL routes: use only those exact paths and never "
           "invent or guess a path; if a requirement needs a route that is not listed, skip that requirement's test.")
FUNCTIONAL = Step("write_functional_tests", "You are a QA engineer. Cover happy paths, edge cases, boundaries, "
                  "error handling and state transitions. " + _COMMON, WriteIn, WriteOut)
SECURITY = Step("write_security_tests", "You are a security tester. Cover injection (SQL, command), broken auth "
                "and access control, IDOR, input validation, secrets exposure and rate limiting. " + _COMMON,
                WriteIn, WriteOut)
STEPS = {"functional": FUNCTIONAL, "security": SECURITY}

CONVENTIONS = {
    "docker-api": "pytest + httpx, tests/*.py, base URL from os.environ['BASE_URL'].",
    "nextjs": "vitest (unit/API via fetch) and playwright (e2e), tests/*.test.ts, base URL from process.env.BASE_URL.",
}


class GenerationError(ValueError):
    pass


def valid_code(code: str, stack: StackName) -> bool:
    if stack == "docker-api":
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return False
        return any(isinstance(n, ast.FunctionDef) and n.name.startswith("test") for n in ast.walk(tree))
    return any(k in code for k in ("test(", "it(", "describe("))


def write_tests(chain: FallbackChain, family: Family, stack: StackName, reqs: list[Requirement],
                rules: list[str] | None = None, surface: str = "") -> list[DraftTest]:
    if family not in STEPS:
        raise GenerationError(f"family {family!r} is not LLM-written")
    allowed = {r.id for r in reqs}
    out = STEPS[family].run(chain, WriteIn(family=family, stack=stack, rules=rules or [], conventions=CONVENTIONS[stack], surface=surface,
                                          requirements=[{"id": r.id, "text": r.text} for r in reqs]))
    drafts = []
    for d in out.tests:
        ids = [i for i in d.requirement_ids if i in allowed]  # never trust cited ids
        if ids and valid_code(d.code, stack):
            drafts.append(d.model_copy(update={"requirement_ids": ids}))
    if not drafts:
        raise GenerationError("model produced no valid tests for the requested requirements")
    return drafts


def to_test_cases(drafts_by_family: list[tuple[Family, list[DraftTest]]], stack: StackName) -> list[TestCase]:
    """Assign stable T-ids and file paths after all workers finish."""
    ext, folder = PROFILES[stack].test_ext, PROFILES[stack].test_dir
    cases, n = [], 0
    for family, drafts in drafts_by_family:
        for d in drafts:
            n += 1
            cases.append(TestCase(id=f"T{n}", requirement_ids=d.requirement_ids, name=d.name, family=family,
                                  file=f"{folder}/test_{family}_{n}{ext}", code=d.code, hint=d.hint))
    return cases
