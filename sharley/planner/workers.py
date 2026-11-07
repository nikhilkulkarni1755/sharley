"""Workers pull tasks, read exact requirement text from the stored spec, and write tests in parallel."""
from concurrent.futures import ThreadPoolExecutor

from sharley.generator import DraftTest, env_tests, to_test_cases, write_tests
from sharley.harness import FallbackChain
from sharley.harness.budget import BudgetExceeded
from sharley.intake.codebase import render_summary, summarize_codebase
from sharley.planner.queue import TaskQueue
from sharley.planner.tasks import Task, plan
from sharley.planner.traceability import TraceReport, trace
from sharley.schemas import Spec, TestCase
from sharley.schemas.spec import StackName
from sharley.storage.repository import Repository

SURFACE_CHARS = 8000
DEFAULT_WORKERS = 8  # tasks are independent LLM calls; 12+ tasks per bank, so more workers cut wall-clock directly


class Worker:
    def __init__(self, repo: Repository, chain: FallbackChain, stack: StackName, files: dict[str, str] | None = None,
                 rules: list[str] | None = None, surface: str = ""):
        self.queue, self.repo, self.chain = TaskQueue(repo), repo, chain
        self.stack, self.files, self.rules, self.surface = stack, files or {}, rules or [], surface

    def run_task(self, task: Task) -> None:
        try:
            spec = Spec.model_validate(self.repo.get("specs", task.spec_hash))
            reqs = [spec.get(i) for i in task.requirement_ids]  # exact text, never a summary
            if task.family == "env":
                drafts = env_tests(self.files, self.stack, task.requirement_ids)
            else:
                drafts = write_tests(self.chain, task.family, self.stack, reqs, self.rules, self.surface, spec.source_excerpt)
            self.queue.complete(task.id, [d.model_dump() for d in drafts])
        except Exception as e:  # one bad task must not kill the worker; traceability reports the gap
            self.queue.fail(task.id, f"{type(e).__name__}: {e}")

    def run(self) -> int:
        n = 0
        while (task := self.queue.claim()) is not None:
            self.run_task(task)
            n += 1
        return n


def generate_test_cases(spec: Spec, repo: Repository, chain: FallbackChain, *, stack: StackName | None = None,
                        files: dict[str, str] | None = None, rules: list[str] | None = None,
                        workers: int = DEFAULT_WORKERS) -> tuple[list[TestCase], TraceReport]:
    stack = stack or spec.stack
    if stack is None:
        raise ValueError("stack unknown: pass stack= or use a spec with a detected stack")
    repo.put("specs", spec.spec_hash, spec.model_dump())
    surface = render_summary(summarize_codebase(files))[:SURFACE_CHARS] if files else ""
    tasks = plan(spec)
    queue = TaskQueue(repo)
    queue.enqueue(tasks)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        list(pool.map(lambda _: Worker(repo, chain, stack, files, rules, surface).run(), range(max(1, workers))))
    for doc in queue.results(tasks):
        if doc["status"] == "failed" and "spend cap" in doc["error"]:
            raise BudgetExceeded(doc["error"][:200])  # not "incomplete bank": no retry can help until the cap is raised
    by_family = [(t.family, [DraftTest.model_validate(d) for d in doc["drafts"]])
                 for t, doc in zip(tasks, queue.results(tasks)) if doc["status"] == "done"]
    cases = to_test_cases(by_family, stack)
    return cases, trace(spec, cases)
