"""Run a test suite against the correct app and against each mutant."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import tempfile

from sharley.mutation.generate import apply_mutant
from sharley.runner.base import RunReport, Sandbox
from sharley.schemas import Mutant, TestCase
from sharley.schemas.spec import StackName


@dataclass
class EvalResult:
    reference: RunReport
    mutants: list[Mutant]  # killed=True/False; None when the mutant could not boot (excluded from scores)


def run_mutant(sandbox: Sandbox, app_dir: Path, tests: list[TestCase], mutant: Mutant, stack: StackName,
               timeout_s: int) -> Mutant:
    with tempfile.TemporaryDirectory(prefix="sharley-mut-") as tmp:
        dest = apply_mutant(app_dir, mutant, Path(tmp) / "app")
        report = sandbox.run(dest, tests, stack, timeout_s=timeout_s)
    if not report.boot_ok:
        return mutant.model_copy(update={"killed": None})
    killed = report.timed_out or any(not r.passed for r in report.results)
    return mutant.model_copy(update={"killed": killed})


def evaluate(sandbox: Sandbox, app_dir: Path, tests: list[TestCase], mutants: list[Mutant], *,
             stack: StackName = "docker-api", workers: int = 4, timeout_s: int = 180) -> EvalResult:
    reference = sandbox.run(app_dir, tests, stack, timeout_s=timeout_s)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        done = list(pool.map(lambda m: run_mutant(sandbox, app_dir, tests, m, stack, timeout_s), mutants))
    return EvalResult(reference=reference, mutants=done)
