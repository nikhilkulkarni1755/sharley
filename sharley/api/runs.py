"""In-memory run registry: a judging run publishes events that the SSE endpoint streams."""
import threading
import uuid
from dataclasses import dataclass, field

from sharley.runner.base import RunReport, Sandbox


class RecordingSandbox(Sandbox):
    """Wraps a sandbox and remembers the last report so the API can stream per-test results."""
    name = "recording"

    def __init__(self, inner: Sandbox):
        self.inner, self.last = inner, None

    def health(self):
        return self.inner.health()

    def run(self, workspace, tests, stack, *, timeout_s=180) -> RunReport:
        self.last = self.inner.run(workspace, tests, stack, timeout_s=timeout_s)
        return self.last


@dataclass
class Run:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    events: list[dict] = field(default_factory=list)
    done: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def emit(self, event: dict) -> None:
        with self.lock:
            self.events.append(event)

    def finish(self) -> None:
        self.done = True

    def snapshot(self, start: int) -> list[dict]:
        with self.lock:
            return self.events[start:]


class RunRegistry:
    MAX_RUNS = 200

    def __init__(self):
        self.runs: dict[str, Run] = {}

    def create(self) -> Run:
        if len(self.runs) >= self.MAX_RUNS:
            self.runs.pop(next(iter(self.runs)))
        run = Run()
        self.runs[run.id] = run
        return run

    def get(self, run_id: str) -> Run | None:
        return self.runs.get(run_id)


def result_events(bank, report, verdict, rejected: list[str]) -> list[dict]:
    """The SSE event stream for one judged run: example tiles, sealed tiles (position only), then the verdict."""
    from sharley.judge import ordered_sealed

    events = []
    if report is not None and report.results:
        by_id = {r.test_id: r for r in report.results}
        events += [{"type": "example", "id": t.id, "name": t.name, "passed": bool(by_id.get(t.id) and by_id[t.id].passed)}
                   for t in bank.examples]
        events += [{"type": "sealed", "index": i, "passed": bool(by_id.get(t.id) and by_id[t.id].passed)}
                   for i, t in enumerate(ordered_sealed(bank), 1)]
    events.append({"type": "verdict", "verdict": verdict.model_dump(), "summary": verdict.summary(), "rejected_paths": rejected})
    return events
