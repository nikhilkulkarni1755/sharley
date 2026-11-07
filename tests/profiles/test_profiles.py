import json

import pytest
import yaml

from sharley.profiles import PROFILES, Contract, build_contract, detect_stack


def test_exactly_two_profiles():
    assert set(PROFILES) == {"nextjs", "docker-api"}
    assert PROFILES["nextjs"].test_frameworks == ["vitest", "playwright"]
    assert PROFILES["docker-api"].test_frameworks == ["pytest"]


def test_detects_nextjs_from_dependencies_or_devdependencies():
    assert detect_stack({"package.json": json.dumps({"dependencies": {"next": "15"}})}) == "nextjs"
    assert detect_stack({"package.json": json.dumps({"devDependencies": {"next": "15"}})}) == "nextjs"


def test_detects_docker_api():
    files = {"Dockerfile": "FROM python", "requirements.txt": "fastapi==0.1\nuvicorn"}
    assert detect_stack(files) == "docker-api"
    assert detect_stack({"Dockerfile": "x", "pyproject.toml": "dependencies=['Flask']"}) == "docker-api"


@pytest.mark.parametrize("files", [
    {},
    {"package.json": json.dumps({"dependencies": {"react": "19"}})},
    {"requirements.txt": "fastapi"},  # no Dockerfile
    {"Dockerfile": "x", "requirements.txt": "requests"},  # no web framework
])
def test_unsupported_projects_are_not_guessed(files):
    assert detect_stack(files) is None


def test_malformed_package_json_does_not_crash():
    assert detect_stack({"package.json": "{not json"}) is None


def test_package_name_lookalike_is_not_next():
    assert detect_stack({"package.json": json.dumps({"dependencies": {"next-auth": "1"}})}) is None


def test_contract_roundtrips_and_dedupes_env():
    text = build_contract("docker-api", ["DB_URL", "SECRET", "DB_URL"])
    c = Contract.model_validate(yaml.safe_load(text))
    assert c.required_env == ["DB_URL", "SECRET"]
    assert c.health == "http://localhost:8000/health"
    assert c.test == ["pytest -q tests"]


def test_contract_rejects_unknown_stack():
    with pytest.raises(KeyError):
        build_contract("rails")  # type: ignore[arg-type]
