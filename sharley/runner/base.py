"""Sandbox interface and result types."""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal

from pydantic import Field

from sharley.schemas.spec import StackName, Strict
from sharley.schemas.testbank import TestCase


class TestResult(Strict):
    __test__ = False

    test_id: str
    passed: bool
    kind: Literal["pass", "assert", "runtime"]
    output: str = ""
    duration_s: float = 0.0


class RunReport(Strict):
    boot_ok: bool = True
    timed_out: bool = False
    build_output: str = ""
    results: list[TestResult] = Field(default_factory=list)


class Sandbox(ABC):
    name: str

    @abstractmethod
    def health(self) -> bool: ...

    @abstractmethod
    def run(self, workspace: Path, tests: list[TestCase], stack: StackName, *, timeout_s: int = 180) -> RunReport:
        """Run tests against the app in workspace, isolated. Never raise for app/test failures."""
