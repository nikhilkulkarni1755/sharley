"""Task queue over the repository (MongoDB-backed, JSON fallback)."""
from sharley.planner.tasks import Task
from sharley.storage.repository import Repository


class TaskQueue:
    def __init__(self, repo: Repository):
        self.repo = repo

    def enqueue(self, tasks: list[Task]) -> None:
        for t in tasks:
            self.repo.put("queue", t.id, {**t.model_dump(), "status": "pending", "drafts": [], "error": ""})

    def claim(self) -> Task | None:
        got = self.repo.claim("queue")
        if got is None:
            return None
        _, doc = got
        return Task.model_validate({k: doc[k] for k in ("id", "spec_hash", "family", "requirement_ids")})

    def complete(self, task_id: str, drafts: list[dict]) -> None:
        self._finish(task_id, "done", drafts=drafts)

    def fail(self, task_id: str, error: str) -> None:
        self._finish(task_id, "failed", error=error[:500])

    def _finish(self, task_id: str, status: str, **fields) -> None:
        doc = self.repo.get("queue", task_id)
        if doc is None:
            raise KeyError(task_id)
        self.repo.put("queue", task_id, {**doc, "status": status, **fields})

    def results(self, tasks: list[Task]) -> list[dict]:
        return [self.repo.get("queue", t.id) for t in tasks]
