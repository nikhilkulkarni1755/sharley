import json

import pytest

from sharley.intake.codebase import env_refs, openapi_routes, router_prefixes, summarize_codebase
from sharley.profiles import detect_stack

FASTAPI_PKG = {
    "app/main.py": "app.include_router(api_router, prefix=settings.api_prefix)",
    "app/api/api.py": ('router = APIRouter()\nrouter.include_router(auth.router, tags=["a"], prefix="/users")\n'
                       'router.include_router(\n    articles.router,\n    prefix="/articles",\n)\n'),
    "app/api/auth.py": 'router = APIRouter()\n@router.post("/login")\ndef login(): ...\n@router.post("")\ndef register(): ...',
    "app/api/articles.py": 'router = APIRouter()\n@router.get("/{slug}")\ndef get(): ...',
    "tests/test_x.py": '@router.get("/should-not-appear")\ndef test_x(): ...',
}


def test_router_prefixes_resolve_including_multiline_and_empty_paths():
    s = summarize_codebase(FASTAPI_PKG)
    assert set(s.routes) == {"POST /users/login", "POST /users", "GET /articles/{slug}"}


def test_nested_include_prefixes_are_composed():
    files = {"a/top.py": 'router.include_router(mid.router, prefix="/v1")', "a/mid.py": 'router.include_router(leaf.router, prefix="/items")',
             "a/leaf.py": 'router = APIRouter()\n@router.get("/{id}")\ndef g(): ...'}
    assert router_prefixes(files)["leaf"] == "/v1/items"
    assert summarize_codebase(files).routes == ["GET /v1/items/{id}"]


def test_include_cycles_do_not_hang():
    files = {"a.py": "router.include_router(b.router, prefix='/x')", "b.py": "router.include_router(a.router, prefix='/y')"}
    assert isinstance(router_prefixes(files), dict)


def test_apirouter_own_prefix_and_test_files_excluded():
    files = {"u.py": 'router = APIRouter(prefix="/users", tags=["u"])\n@router.get("/me")\ndef me(): ...'}
    assert summarize_codebase(files).routes == ["GET /users/me"]


def test_openapi_yaml_and_json_routes_and_garbage():
    yml = "openapi: 3.0.0\npaths:\n  /books/v1:\n    get: {}\n    post: {}\n    parameters: []\n  /users/{id}:\n    delete: {}\n"
    js = json.dumps({"paths": {"/h": {"get": {}}}})
    got = openapi_routes({"openapi_specs/openapi3.yml": yml, "api/swagger.json": js, "openapi.yaml": ":: not yaml ::\n\t-", "x.txt": yml})
    assert got == {"GET /books/v1", "POST /books/v1", "DELETE /users/{id}", "GET /h"}


def test_pydantic_settings_fields_become_env_vars_but_tests_are_ignored():
    files = {"core/config.py": 'class Settings(BaseSettings):\n    model_config = x\n    SECRET_KEY: str\n    db_url: str = "x"\n    _private: int = 1\n',
             "core/other.py": "class AppSettings(BaseAppSettings):\n    debug: bool = False\n",
             "tests/test_a.py": 'import os\nos.environ["ONLY_IN_TESTS"]', "web/app.spec.ts": "process.env.ONLY_IN_SPEC",
             "svc.py": 'database_url = config("DATABASE_URL", cast=str)'}
    assert set(env_refs(files)) == {"SECRET_KEY", "DB_URL", "DEBUG", "DATABASE_URL"}


def test_sqlmodel_and_base_classes_are_schemas_and_react_components_are_not_functions():
    files = {"models.py": "class User(UserBase, table=True):\n    id: int\nclass Item(SQLModel):\n    x: int\nclass Plain:\n    pass",
             "ui/Button.tsx": "function Button() {}", "lib/util.ts": "function helper() {}", "tests/test_a.py": "def test_a(): ..."}
    s = summarize_codebase(files)
    assert s.schemas == ["Item", "User"] and s.functions == ["helper"]


@pytest.mark.parametrize("files,expected", [
    ({"backend/pyproject.toml": 'dependencies=["fastapi"]', "Dockerfile": "FROM python"}, "docker-api"),
    ({"backend/requirements.txt": "flask", "backend/Dockerfile": "FROM python"}, "docker-api"),
    ({"frontend/package.json": json.dumps({"dependencies": {"next": "15"}})}, "nextjs"),
    ({"backend/pyproject.toml": 'dependencies=["fastapi"]'}, None),  # no Dockerfile anywhere
    ({"frontend/package.json": json.dumps({"dependencies": {"react": "19"}}), "Dockerfile": "x"}, None),
])
def test_monorepo_stack_detection(files, expected):
    assert detect_stack(files) == expected


PAY = '''
class NewUser(BaseModel):
    name: str = Field(min_length=1)
    limit: int | None = Field(default=None, gt=0)
    note: str = "hi"


@app.post("/users", status_code=201)
def create(u: NewUser, who: dict = Depends(auth), request: Request = None):
    return {"id": 1, "secret": "x"}


@app.get("/users/{uid}")
async def get(uid: int):
    return {"name": "n"}
'''


def test_request_bodies_model_fields_and_response_keys_reach_the_surface():
    from sharley.intake.codebase import render_summary
    s = summarize_codebase({"app/main.py": PAY})
    assert s.request_bodies == ["POST /users: NewUser"]
    assert "name: str (required)" in s.models["NewUser"]
    assert "limit: int | None = Field(default=None, gt=0)" in s.models["NewUser"] and 'note: str = "hi"' in s.models["NewUser"]
    assert s.response_keys == ["GET /users/{uid}: name", "POST /users: id, secret"]
    text = render_summary(s)
    assert "send exactly these field names" in text and "NewUser(name: str (required)" in text and "POST /users: id, secret" in text


def test_non_model_params_and_tests_are_not_request_bodies():
    files = {"app/x.py": '@app.get("/a")\ndef a(q: str, d: Depends): return {"k": 1}', "tests/t.py": PAY}
    assert summarize_codebase(files).request_bodies == []


def test_error_hints_tell_the_writer_which_route_rejects_what():
    code = ('@app.post("/auth/signup")\ndef signup(p):\n    if p.kind != "user":\n'
            '        raise HTTPException(status_code=403, detail="agents are created by their owner")\n    return {"id": 1}\n'
            '@app.post("/principals")\ndef make(p):\n    raise HTTPException(status_code=422, detail="agents need a limit")\n')
    s = summarize_codebase({"app/main.py": code})
    assert s.error_hints == ["POST /auth/signup: 403 agents are created by their owner", "POST /principals: 422 agents need a limit"]
    from sharley.intake.codebase import render_summary
    assert "POST /auth/signup: 403 agents are created by their owner" in render_summary(s)
