"""Canonical spec: the single source of truth every downstream step cites by ID."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from sharley.hashing import sha256_json

Category = Literal["functional", "security", "deployment", "data"]
StackName = Literal["nextjs", "docker-api"]
REQ_ID = r"^R\d+$"
ASSUMPTION_ID = r"^A\d+$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _drop_computed(cls, data):
        """Dumps include computed fields (hashes); accept them on reload and recompute."""
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k not in cls.model_computed_fields}
        return data


class Evidence(Strict):
    kind: Literal["observed", "inferred"]
    source_span: str | None = None
    assumption_id: str | None = Field(default=None, pattern=ASSUMPTION_ID)

    @model_validator(mode="after")
    def _kind_matches_fields(self) -> "Evidence":
        if self.kind == "observed" and not (self.source_span or "").strip():
            raise ValueError("observed evidence needs a quoted source_span")
        if self.kind == "inferred" and not self.assumption_id:
            raise ValueError("inferred evidence needs an assumption_id")
        return self


class Requirement(Strict):
    id: str = Field(pattern=REQ_ID)
    text: str = Field(min_length=3)
    category: Category
    evidence: Evidence


class IgnoredSpan(Strict):
    span: str
    reason: str = Field(min_length=3)


class Spec(Strict):
    version: int = Field(default=1, ge=1)
    stack: StackName | None = None
    source_hash: str
    requirements: list[Requirement] = Field(min_length=1)
    assumptions: dict[str, str] = Field(default_factory=dict)
    ignored: list[IgnoredSpan] = Field(default_factory=list)
    coverage_pct: float = Field(default=100.0, ge=0, le=100)
    source_excerpt: str = Field(default="", max_length=6000)  # the original spec text, so writers can read credentials/ids/setup facts verbatim

    @model_validator(mode="after")
    def _consistent(self) -> "Spec":
        ids = [r.id for r in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate requirement ids")
        for r in self.requirements:
            aid = r.evidence.assumption_id
            if aid and aid not in self.assumptions:
                raise ValueError(f"{r.id} cites unknown assumption {aid}")
        return self

    @computed_field
    @property
    def spec_hash(self) -> str:
        return sha256_json(self.model_dump(exclude={"spec_hash"}))

    def get(self, requirement_id: str) -> Requirement:
        for r in self.requirements:
            if r.id == requirement_id:
                return r
        raise KeyError(requirement_id)
