import json
import threading

import pytest
from pydantic import ValidationError

from sharley.harness import FallbackChain
from sharley.harness.provider import ModelProvider
from sharley.planner import Task, TaskQueue, Worker, generate_test_cases, plan, trace
from sharley.schemas import Evidence, Requirement, Spec, TestCase
from sharley.storage import JsonRepository
from tests.fakes import ScriptedProvider

OBS = Evidence(kind="observed", source_span="x")
GOOD = "def test_it():\n    assert True\n"


def mkspec(cats):
    reqs = [Requirement(id=f"R{i}", text=f"Requirement number {i}", category=c, evidence=OBS) for i, c in enumerate(cats, 1)]
    return Spec(source_hash="s", requirements=reqs, stack="docker-api")


class EchoProvider(ModelProvider):
    """Writes one valid test per requirement id found in the prompt (thread-safe)."""
    name, model, family = "echo", "echo", "fake"

    def health(self):
        return True

    def complete(self, system, user, *, images=None):
        import re
        ids = sorted(set(re.findall(r'"id":"(R\d+)"', user)))
        return json.dumps({"tests": [{"name": f"t {i}", "code": GOOD, "requirement_ids": [i], "hint": "h"} for i in ids]})


# ---- plan
def test_plan_groups_by_family_in_small_batches():
    spec = mkspec(["functional"] * 4 + ["security", "data", "deployment"])
    tasks = plan(spec)
    assert [(t.family, t.requirement_ids) for t in tasks] == [
        ("functional", ["R1", "R2", "R3"]), ("functional", ["R4", "R6"]),
        ("security", ["R5"]), ("env", ["R7"])]
    assert len({t.id for t in tasks}) == len(tasks)


def test_plan_covers_every_requirement_exactly_once():
    spec = mkspec(["functional", "security", "deployment", "data"] * 5)
    cited = [i for t in plan(spec, batch=2) for i in t.requirement_ids]
    assert sorted(cited) == sorted(r.id for r in spec.requirements)


def test_bad_batch_and_empty_task_rejected():
    with pytest.raises(ValueError):
        plan(mkspec(["functional"]), batch=0)
    with pytest.raises(ValidationError):
        Task(id="k", spec_hash="h", family="functional", requirement_ids=[])


# ---- queue
def test_queue_lifecycle(tmp_path):
    q = TaskQueue(JsonRepository(tmp_path))
    t = plan(mkspec(["functional"]))[0]
    q.enqueue([t])
    got = q.claim()
    assert got == t and q.claim() is None
    q.complete(t.id, [{"x": 1}])
    assert q.results([t])[0]["status"] == "done"
    with pytest.raises(KeyError):
        q.fail("missing", "e")


# ---- end to end
def test_parallel_generation_is_traceable_and_complete(tmp_path):
    spec = mkspec(["functional"] * 7 + ["security"] * 4 + ["deployment"])
    repo = JsonRepository(tmp_path)
    cases, report = generate_test_cases(spec, repo, FallbackChain([EchoProvider()]), workers=4)
    assert report.ok and report.uncovered == []
    assert len(cases) == 12 and len({c.id for c in cases}) == len(cases)
    assert {c.family for c in cases} == {"functional", "security", "env"}


def test_workers_read_exact_spec_text_from_storage(tmp_path):
    spec = mkspec(["functional"])
    p = ScriptedProvider("p", [json.dumps({"tests": [{"name": "a", "code": GOOD, "requirement_ids": ["R1"]}]})])
    generate_test_cases(spec, JsonRepository(tmp_path), FallbackChain([p]), workers=1)
    assert "Requirement number 1" in p.calls[0][1]


def test_failed_task_is_reported_as_uncovered_not_crashed(tmp_path):
    spec = mkspec(["functional", "security"])
    p = ScriptedProvider("p", [json.dumps({"tests": [{"name": "a", "code": GOOD, "requirement_ids": ["R1"]}]})])
    repo = JsonRepository(tmp_path)
    cases, report = generate_test_cases(spec, repo, FallbackChain([p]), workers=1)
    assert [c.requirement_ids for c in cases] == [["R1"]]
    assert report.uncovered == ["R2"] and not report.ok
    failed = [d for d in repo.find("queue") if d["status"] == "failed"]
    assert len(failed) == 1 and failed[0]["error"]


def test_generation_requires_a_stack(tmp_path):
    spec = Spec(source_hash="s", requirements=mkspec(["functional"]).requirements)
    with pytest.raises(ValueError, match="stack"):
        generate_test_cases(spec, JsonRepository(tmp_path), FallbackChain([EchoProvider()]))
    cases, _ = generate_test_cases(spec, JsonRepository(tmp_path), FallbackChain([EchoProvider()]), stack="docker-api")
    assert cases


def test_tasks_for_unknown_spec_fail_cleanly(tmp_path):
    repo = JsonRepository(tmp_path)
    q = TaskQueue(repo)
    t = Task(id="k1", spec_hash="nope", family="functional", requirement_ids=["R1"])
    q.enqueue([t])
    Worker(repo, FallbackChain([EchoProvider()]), "docker-api").run()
    assert repo.get("queue", "k1")["status"] == "failed"


def test_concurrent_workers_never_run_a_task_twice(tmp_path):
    spec = mkspec(["functional"] * 30)
    repo = JsonRepository(tmp_path)
    repo.put("specs", spec.spec_hash, spec.model_dump())
    q = TaskQueue(repo)
    q.enqueue(plan(spec, batch=1))
    counts, lock = [], threading.Lock()

    def go():
        n = Worker(repo, FallbackChain([EchoProvider()]), "docker-api").run()
        with lock:
            counts.append(n)

    ts = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sum(counts) == 30


# ---- traceability
def tc(ids):
    return TestCase(id="T1", requirement_ids=ids, name="n", family="functional", file="tests/a.py", code="x")


def test_trace_flags_uncovered_and_unknown_refs():
    spec = mkspec(["functional", "functional", "security"])
    r = trace(spec, [tc(["R1", "R9"])])
    assert r.uncovered == ["R2", "R3"] and r.unknown_refs == ["R9"] and not r.ok
    assert trace(spec, [tc(["R1", "R2", "R3"])]).ok


def test_trace_sorts_ids_numerically():
    spec = mkspec(["functional"] * 11)
    assert trace(spec, []).uncovered[-2:] == ["R10", "R11"]


def test_generate_passes_codebase_surface_to_workers(tmp_path):
    spec = mkspec(["functional"])
    p = ScriptedProvider("p", [json.dumps({"tests": [{"name": "a", "code": GOOD, "requirement_ids": ["R1"]}]})])
    files = {"app.py": '@app.post("/real/path")\ndef f(): ...'}
    generate_test_cases(spec, JsonRepository(tmp_path), FallbackChain([p]), files=files, workers=1)
    assert "POST /real/path" in p.calls[0][1]


def test_workers_pass_the_stored_spec_source_to_the_writer(tmp_path):
    spec = mkspec(["functional"]).model_copy(update={"source_excerpt": "Key is operator-key"})
    p = ScriptedProvider("p", [json.dumps({"tests": [{"name": "a", "code": GOOD, "requirement_ids": ["R1"]}]})])
    generate_test_cases(spec, JsonRepository(tmp_path), FallbackChain([p]), workers=1)
    assert "Key is operator-key" in p.calls[0][1]
