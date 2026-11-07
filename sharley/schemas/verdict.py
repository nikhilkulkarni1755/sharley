"""Verdicts, model identity, mutants and skill versions."""
from typing import Literal

from pydantic import Field, computed_field, model_validator

from sharley.schemas.spec import Strict

PRODUCTION_THRESHOLD = 0.90
Status = Literal[
    "Accepted",
    "Wrong Answer",
    "Runtime Error",
    "Time Limit Exceeded",
    "Build Failed",
    "Rejected: tests tampered",
]


class ModelRef(Strict):
    provider: str
    model: str
    family: str


class Verdict(Strict):
    status: Status
    failed_test_index: int | None = Field(default=None, ge=1)
    total_sealed: int = Field(ge=0)
    requirement_ids: list[str] = Field(default_factory=list)
    hint: str = ""
    example_passed: int = Field(default=0, ge=0)
    example_total: int = Field(default=0, ge=0)
    implementer: ModelRef
    verifier: ModelRef
    seed: int
    spec_hash: str

    @model_validator(mode="after")
    def _valid(self) -> "Verdict":
        if self.implementer.family == self.verifier.family:
            raise ValueError("implementer and verifier must be different model families")
        if self.status == "Wrong Answer" and self.failed_test_index is None:
            raise ValueError("Wrong Answer needs failed_test_index")
        if self.failed_test_index and self.failed_test_index > self.total_sealed:
            raise ValueError("failed_test_index exceeds total_sealed")
        if self.example_passed > self.example_total:
            raise ValueError("example_passed exceeds example_total")
        return self

    def summary(self) -> str:
        if self.status == "Wrong Answer":
            reqs = ", ".join(self.requirement_ids)
            return f"Wrong Answer on sealed test {self.failed_test_index} of {self.total_sealed}: {self.hint} ({reqs})"
        return self.status


class Mutant(Strict):
    id: str
    operator: str
    category: Literal["functional", "security"]
    file: str
    line: int = Field(ge=1)
    original: str
    mutated: str
    split: Literal["train", "heldout"]
    killed: bool | None = None


class Scores(Strict):
    heldout_mutation_score: float = Field(ge=0, le=1)
    false_failure_rate: float = Field(ge=0, le=1)
    security_kill_rate: float = Field(ge=0, le=1)

    @computed_field
    @property
    def production_worthy(self) -> float:
        return self.heldout_mutation_score * (1 - self.false_failure_rate)


class SkillVersion(Strict):
    version: int = Field(ge=0)
    parent: int | None = None
    rules: list[str]
    diff: str = ""
    scores: Scores | None = None
    decision: Literal["baseline", "adopted", "rolled_back"]
    reason: str = ""

    @model_validator(mode="after")
    def _lineage(self) -> "SkillVersion":
        if self.version > 0 and self.parent is None:
            raise ValueError("non-baseline versions need a parent")
        if self.decision == "rolled_back" and not self.reason:
            raise ValueError("a rollback must log its reason")
        return self
