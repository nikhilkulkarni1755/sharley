"""Every requirement is covered by at least one test; every test cites real requirements."""
from pydantic import BaseModel

from sharley.schemas import Spec, TestCase


class TraceReport(BaseModel):
    uncovered: list[str]
    unknown_refs: list[str]

    @property
    def ok(self) -> bool:
        return not self.uncovered and not self.unknown_refs


def trace(spec: Spec, tests: list[TestCase]) -> TraceReport:
    known = {r.id for r in spec.requirements}
    cited = {i for t in tests for i in t.requirement_ids}
    return TraceReport(uncovered=sorted(known - cited, key=lambda x: int(x[1:])), unknown_refs=sorted(cited - known))
