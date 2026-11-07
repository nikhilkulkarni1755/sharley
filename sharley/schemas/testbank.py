"""Test cases and the example/sealed split (the LeetCode model)."""
import re
from typing import Literal

from pydantic import Field, computed_field, model_validator

from sharley.hashing import sha256_text
from sharley.schemas.spec import REQ_ID, Strict
from sharley.schemas.verdict import ModelRef

Family = Literal["functional", "security", "env"]
Visibility = Literal["example", "sealed"]


class TestCase(Strict):
    __test__ = False  # not a pytest class

    id: str = Field(pattern=r"^T\d+$")
    requirement_ids: list[str] = Field(min_length=1)
    name: str = Field(min_length=1)
    family: Family
    file: str = Field(min_length=1)
    code: str = Field(min_length=1)
    hint: str = Field(default="", description="Plain-English failure hint; must not reveal test code.")
    visibility: Visibility | None = None

    @model_validator(mode="after")
    def _valid(self) -> "TestCase":
        for rid in self.requirement_ids:
            if not re.match(REQ_ID, rid):
                raise ValueError(f"bad requirement id {rid}")
        if self.file.startswith("/") or ".." in self.file.split("/"):
            raise ValueError("test file path must be relative and inside the workspace")
        return self

    @computed_field
    @property
    def sha256(self) -> str:
        return sha256_text(self.code)


class TestBank(Strict):
    __test__ = False

    spec_hash: str
    seed: int
    example_ratio: float = Field(default=0.3, gt=0, lt=1)
    author: ModelRef | None = None  # the verifier model that wrote these tests
    tests: list[TestCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _split_complete(self) -> "TestBank":
        ids = [t.id for t in self.tests]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate test ids")
        if any(t.visibility is None for t in self.tests):
            raise ValueError("every test must be assigned example or sealed")
        return self

    @property
    def examples(self) -> list[TestCase]:
        return [t for t in self.tests if t.visibility == "example"]

    @property
    def sealed(self) -> list[TestCase]:
        return [t for t in self.tests if t.visibility == "sealed"]

    @computed_field
    @property
    def file_hashes(self) -> dict[str, str]:
        return {t.file: t.sha256 for t in self.tests}
