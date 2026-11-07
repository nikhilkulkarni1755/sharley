"""Run the self-improvement loop for real: regenerate tests under candidate skills, score them on held-out mutants of
the reference app in the Docker sandbox, and adopt or roll back."""
from collections.abc import Callable
from pathlib import Path

from evals.fixtures.build import valid_mutants
from evals.graders import score
from evals.reference import APP_DIR, reference_spec
from sharley.gate.context import Context
from sharley.intake.files import load_codebase
from sharley.mutation import evaluate as run_evaluation
from sharley.planner import generate_test_cases
from sharley.runner.base import Sandbox
from sharley.schemas import Mutant, TestCase
from sharley.skills import LoopResult, SkillStore, improve


def reference_files() -> dict[str, str]:
    """The app's own code (not its oracle tests), as the test writer sees an existing codebase."""
    return {p: t for p, t in load_codebase(APP_DIR).items() if not p.startswith("oracle/")}


def run_improvement(ctx: Context, sandbox: Sandbox, *, scope: str = "global", iters: int = 3, seed: int = 0, workers: int = 4,
                    mutants: list[Mutant] | None = None, generate: Callable[[list[str]], list[TestCase]] | None = None) -> LoopResult:
    spec, files = reference_spec(), reference_files()
    mutants = mutants if mutants is not None else valid_mutants(sandbox, seed, workers)

    def gen(rules: list[str]) -> list[TestCase]:
        tests, _ = generate_test_cases(spec, ctx.repo, ctx.verifier, stack="docker-api", files=files, rules=rules, workers=workers)
        return tests

    return improve(store=SkillStore(ctx.repo, scope), chain=ctx.verifier, generate=generate or gen,
                   evaluate=lambda tests, ms: run_evaluation(sandbox, APP_DIR, tests, ms, workers=workers),
                   score=lambda r: score(r), mutants=mutants, max_iters=iters)
