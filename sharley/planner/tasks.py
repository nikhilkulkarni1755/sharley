"""Deterministic planner: spec -> small test-writing tasks that cite requirement ids."""
from pydantic import Field

from sharley.schemas import Spec
from sharley.schemas.spec import Strict
from sharley.schemas.testbank import Family

FAMILY_OF = {"functional": "functional", "data": "functional", "security": "security", "deployment": "env"}
BATCH = 3  # small batches keep each LLM step tiny enough for small local models


class Task(Strict):
    id: str
    spec_hash: str
    family: Family
    requirement_ids: list[str] = Field(min_length=1)


def plan(spec: Spec, batch: int = BATCH) -> list[Task]:
    if batch < 1:
        raise ValueError("batch must be >= 1")
    tasks: list[Task] = []
    for family in ("functional", "security", "env"):
        ids = [r.id for r in spec.requirements if FAMILY_OF[r.category] == family]
        for i in range(0, len(ids), batch):
            tasks.append(Task(id=f"{spec.spec_hash[:12]}-K{len(tasks) + 1}", spec_hash=spec.spec_hash,
                              family=family, requirement_ids=ids[i:i + batch]))
    return tasks
