from sharley.schemas import Mutant


def mutation_score(mutants: list[Mutant], split: str | None = "heldout") -> float:
    """killed / (killed + survived); mutants that could not boot (killed=None) are excluded."""
    scored = [m for m in mutants if m.killed is not None and (split is None or m.split == split)]
    return sum(m.killed for m in scored) / len(scored) if scored else 0.0
