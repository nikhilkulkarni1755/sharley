from evals.graders.false_failure import false_failure_rate
from evals.graders.mutation_score import mutation_score
from evals.graders.security_score import security_kill_rate
from sharley.mutation import EvalResult
from sharley.schemas import Scores


def score(result: EvalResult, split: str | None = "heldout") -> Scores:
    return Scores(heldout_mutation_score=mutation_score(result.mutants, split),
                  false_failure_rate=false_failure_rate(result.reference),
                  security_kill_rate=security_kill_rate(result.mutants))


__all__ = ["false_failure_rate", "mutation_score", "score", "security_kill_rate"]
