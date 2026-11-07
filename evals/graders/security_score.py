from sharley.schemas import Mutant


def security_kill_rate(mutants: list[Mutant]) -> float:
    sec = [m for m in mutants if m.category == "security" and m.killed is not None]
    return sum(m.killed for m in sec) / len(sec) if sec else 0.0
