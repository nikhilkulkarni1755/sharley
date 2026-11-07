import ast
import json

import pytest

from sharley.generator import GenerationError, check_env, env_tests, to_test_cases, write_tests
from sharley.generator.writer import valid_code
from sharley.harness import FallbackChain, StepFailed
from sharley.schemas import Evidence, Requirement
from tests.fakes import ScriptedProvider

OBS = Evidence(kind="observed", source_span="x")
R1 = Requirement(id="R1", text="Users can create notes", category="functional", evidence=OBS)
R2 = Requirement(id="R2", text="Users cannot read others' notes", category="security", evidence=OBS)
GOOD = "import httpx\n\ndef test_create():\n    assert True\n"


def reply(*tests):
    return json.dumps({"tests": list(tests)})


def draft(code=GOOD, ids=("R1",), name="creates note"):
    return {"name": name, "code": code, "requirement_ids": list(ids), "hint": "notes cannot be created"}


def chain(*replies):
    p = ScriptedProvider("p", list(replies))
    return FallbackChain([p]), p


# ---- writer
def test_writes_valid_drafts_and_injects_skill_rules():
    c, p = chain(reply(draft()))
    out = write_tests(c, "functional", "docker-api", [R1], rules=["always test ownership"])
    assert out[0].requirement_ids == ["R1"]
    assert "always test ownership" in p.calls[0][1] and "R1" in p.calls[0][1]


def test_security_family_uses_security_prompt():
    c, p = chain(reply(draft(ids=("R2",))))
    write_tests(c, "security", "docker-api", [R2])
    assert "IDOR" in p.calls[0][0]


def test_uncited_or_foreign_requirement_ids_are_stripped():
    c, _ = chain(reply(draft(ids=("R1", "R99")), draft(ids=("R99",), name="orphan")))
    out = write_tests(c, "functional", "docker-api", [R1])
    assert [d.requirement_ids for d in out] == [["R1"]]


def test_syntactically_broken_python_is_dropped():
    c, _ = chain(reply(draft(code="def test_x(:\n"), draft(name="ok")))
    assert [d.name for d in write_tests(c, "functional", "docker-api", [R1])] == ["ok"]


def test_all_invalid_raises_instead_of_silently_returning_nothing():
    c, _ = chain(reply(draft(code="print('no tests here')")))
    with pytest.raises(GenerationError):
        write_tests(c, "functional", "docker-api", [R1])


def test_env_family_is_not_llm_written():
    with pytest.raises(GenerationError):
        write_tests(chain()[0], "env", "docker-api", [R1])


def test_model_garbage_surfaces_as_step_failure():
    c, _ = chain("nonsense", "nonsense", "nonsense")
    with pytest.raises(StepFailed):
        write_tests(c, "functional", "docker-api", [R1])


@pytest.mark.parametrize("code,stack,ok", [
    (GOOD, "docker-api", True),
    ("def helper(): pass", "docker-api", False),
    ("import os\nos.system('x'", "docker-api", False),
    ('test("a", () => {})', "nextjs", True),
    ("console.log(1)", "nextjs", False),
])
def test_valid_code_per_stack(code, stack, ok):
    assert valid_code(code, stack) is ok


def test_to_test_cases_assigns_unique_ids_and_stack_paths():
    from sharley.generator import DraftTest
    d = DraftTest(name="a", code=GOOD, requirement_ids=["R1"])
    cases = to_test_cases([("functional", [d, d]), ("security", [d])], "docker-api")
    assert [c.id for c in cases] == ["T1", "T2", "T3"]
    assert cases[0].file == "tests/test_functional_1.py" and cases[2].file == "tests/test_security_3.py"
    ts = to_test_cases([("functional", [d])], "nextjs")
    assert ts[0].file.endswith(".test.ts")


# ---- env check
FILES = {
    "app/main.py": 'import os\nos.environ["DB_URL"]; os.getenv("SECRET"); os.getenv("PORT")',
    ".env.example": "DB_URL=\nPORT=8000\n# SECRET=\n",
    "Dockerfile": "FROM python\nENV PORT=8000\nENV DB_URL=x\nCMD uvicorn",
}


def test_check_env_finds_gaps():
    r = check_env(FILES)
    assert r.referenced == ["DB_URL", "PORT", "SECRET"]
    assert r.missing_from_example == ["SECRET"]  # commented out != declared
    assert r.undeclared_in_deploy == ["SECRET"]


def test_check_env_clean_project_has_no_gaps():
    files = {"a.py": 'import os\nos.getenv("A_KEY")', ".env.example": "A_KEY=\n", "Dockerfile": "ENV A_KEY=1"}
    r = check_env(files)
    assert r.missing_from_example == [] and r.undeclared_in_deploy == []


def test_dockerfile_keywords_are_not_mistaken_for_env_vars():
    r = check_env({"a.py": 'import os\nos.getenv("FROM_X")', "Dockerfile": "FROM python\nRUN x\nEXPOSE 80"})
    assert r.undeclared_in_deploy == ["FROM_X"]


def test_generated_env_tests_are_valid_and_traced():
    (t,) = env_tests(FILES, "docker-api", ["R5"])
    ast.parse(t.code)
    assert t.requirement_ids == ["R5"] and '"SECRET"' in t.code and "/health" in t.code
    (ts,) = env_tests(FILES, "nextjs", ["R5"])
    assert "/api/health" in ts.code and "vitest" in ts.code


def test_env_tests_need_a_requirement_to_trace_to():
    assert env_tests(FILES, "docker-api", []) == []


def test_hostile_env_names_cannot_inject_code_into_generated_tests():
    files = {"a.py": 'import os\nos.getenv("X\\"); import os; os.system(\\"rm -rf /")'}
    (t,) = env_tests(files, "docker-api", ["R1"])
    ast.parse(t.code)
    assert "rm -rf" not in t.code


def test_surface_reaches_the_writer_prompt_and_forbids_inventing_paths():
    c, p = chain(reply(draft()))
    write_tests(c, "functional", "docker-api", [R1], surface="Routes:\n- POST /users/v1/login")
    system, user, _ = p.calls[0]
    assert "POST /users/v1/login" in user and "never invent" in system


def test_greenfield_has_empty_surface():
    c, p = chain(reply(draft()))
    write_tests(c, "functional", "docker-api", [R1])
    assert '"surface":""' in p.calls[0][1]
