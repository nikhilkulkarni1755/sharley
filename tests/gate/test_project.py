import base64
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from sharley.api import create_app
from sharley.gate.context import Context
from sharley.gate.project import build_project_zip, render_spec_md
from sharley.harness import FallbackChain
from sharley.judge import split_bank
from sharley.schemas import Evidence, Requirement, Spec, TestCase
from sharley.storage import JsonRepository
from tests.fakes import EchoWriter, ScriptedProvider
from tests.gate.test_gate import FakeSandbox

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 30
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 30


def spec():
    return Spec(source_hash="s", stack="docker-api", requirements=[
        Requirement(id="R1", text="Users can sign up | and log in", category="functional", evidence=Evidence(kind="observed", source_span="x")),
        Requirement(id="R2", text="Passwords must be hashed", category="security", evidence=Evidence(kind="inferred", assumption_id="A1"))],
        assumptions={"A1": "Industry norm"})


def bank(n=12):
    tests = [TestCase(id=f"T{i}", requirement_ids=["R1"], name=f"name-{i}", family="functional", file=f"tests/test_{i}.py",
                      code=f"def test_{i}():\n    assert 1  # CODE-{i}-END\n", hint=f"hint about {i}") for i in range(1, n + 1)]
    return split_bank(tests, spec().spec_hash, 3)


def unzip(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    return {n: z.read(n).decode("utf-8", "replace") for n in z.namelist()}


def test_zip_has_everything_a_developer_needs():
    b = bank()
    files = unzip(build_project_zip(spec(), b))
    assert {"SPEC.md", "spec.json", "CLAUDE.md", "PROMPT.md", "sharley.yaml", "SHARLEY.md"} <= set(files)
    assert {t.file for t in b.examples} <= set(files)
    assert "uvicorn app.main:app" in files["CLAUDE.md"] and "tests/" in files["PROMPT.md"]
    assert json.loads(files["spec.json"])["requirements"][0]["id"] == "R1"


def test_hidden_tests_never_appear_anywhere_in_the_zip():
    b = bank()
    files = unzip(build_project_zip(spec(), b, JPEG))
    blob = "\n".join(files.values())
    assert b.sealed and b.examples
    for t in b.sealed:
        assert t.file not in files
        for secret in (f"CODE-{t.id[1:]}-END", t.name, t.hint):
            assert secret not in blob, f"sealed {t.id} leaked {secret!r}"
    assert all(f"CODE-{t.id[1:]}-END" in files[t.file] for t in b.examples)


def test_export_is_deterministic():
    assert build_project_zip(spec(), bank()) == build_project_zip(spec(), bank())


def test_photo_is_included_with_the_right_extension_and_mentioned_in_the_brief():
    for data, ext in ((JPEG, "jpg"), (PNG, "png")):
        files = unzip(build_project_zip(spec(), bank(), data))
        assert f"reference/photo.{ext}" in files and f"reference/photo.{ext}" in files["CLAUDE.md"]
    assert not any(n.startswith("reference/") for n in unzip(build_project_zip(spec(), bank())))
    assert "original photo" not in unzip(build_project_zip(spec(), bank()))["CLAUDE.md"]


@pytest.mark.parametrize("bad", [b"", b"<svg onload=1>", b"%PDF-1.7", b"GIF89a", b"\xff\xd8\xff" + b"0" * 9_000_000])
def test_non_images_and_oversized_images_are_refused(bad):
    with pytest.raises(ValueError):
        build_project_zip(spec(), bank(), bad)


def test_spec_markdown_marks_assumptions_and_escapes_table_breaking_text():
    md = render_spec_md(spec())
    assert "ASSUMED (A1)" in md and "Users can sign up \\| and log in" in md and "**A1**: Industry norm" in md


def test_zip_member_names_are_safe_relative_paths():
    for n in unzip(build_project_zip(spec(), bank(), PNG)):
        assert not n.startswith("/") and ".." not in n.split("/")


# ---- API
def client(tmp_path):
    ctx = Context(env={}, repo=JsonRepository(tmp_path), verifier=FallbackChain([EchoWriter()]),
                  long_context=FallbackChain([ScriptedProvider("s")]), sandbox=FakeSandbox())
    s, b = spec(), bank()
    ctx.repo.put("specs", s.spec_hash, s.model_dump())
    from sharley.judge import save_bank
    key = save_bank(ctx.repo, b)
    return TestClient(create_app(ctx)), key, b


def test_download_endpoint_returns_a_zip_without_hidden_tests(tmp_path):
    c, key, b = client(tmp_path)
    r = c.post(f"/api/banks/{key}/project", json={"image_b64": base64.b64encode(JPEG).decode()})
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert r.headers["content-disposition"].startswith('attachment; filename="sharley-project-')
    files = unzip(r.content)
    assert "reference/photo.jpg" in files and not {t.file for t in b.sealed} & set(files)
    assert all(f"CODE-{t.id[1:]}-END" not in "\n".join(files.values()) for t in b.sealed)
    assert c.post(f"/api/banks/{key}/project", json={}).status_code == 200  # photo is optional


def test_download_endpoint_misuse(tmp_path):
    c, key, _ = client(tmp_path)
    assert c.post("/api/banks/nope:0/project", json={}).status_code == 404
    assert c.post(f"/api/banks/{key}/project", json={"image_b64": "not base64!!"}).status_code == 422
    assert c.post(f"/api/banks/{key}/project", json={"image_b64": base64.b64encode(b"<svg onload=1>").decode()}).status_code == 422
