"""Improve test-writing skills; adopt a version only if held-out evaluation confirms it, else roll back."""
from collections.abc import Callable
from dataclasses import dataclass

from sharley.harness import FallbackChain, StepFailed
from sharley.mutation import EvalResult
from sharley.schemas import Mutant, Scores, SkillVersion, TestCase
from sharley.skills.reflect import BadRule, propose_rule
from sharley.skills.store import SkillStore, diff_rules

Generate = Callable[[list[str]], list[TestCase]]
Evaluate = Callable[[list[TestCase], list[Mutant]], EvalResult]
Score = Callable[[EvalResult], Scores]

MIN_GAIN = 0.01
MAX_ITERS = 5
PLATEAU = 2  # consecutive non-adopted iterations that end the loop


@dataclass
class LoopResult:
    final: SkillVersion
    timeline: list[SkillVersion]


def decide(cur: Scores, cand: Scores, min_gain: float = MIN_GAIN) -> tuple[bool, str]:
    """Adopt only on a real held-out gain with no increase in false failures."""
    gain = cand.production_worthy - cur.production_worthy
    if cand.false_failure_rate > cur.false_failure_rate:
        return False, (f"false failure rate rose from {cur.false_failure_rate:.2f} to "
                       f"{cand.false_failure_rate:.2f}")
    if gain <= min_gain:
        return False, (f"held-out production-worthy score {cand.production_worthy:.3f} did not beat "
                       f"{cur.production_worthy:.3f} by more than {min_gain}")
    return True, f"held-out production-worthy score rose {cur.production_worthy:.3f} -> {cand.production_worthy:.3f}"


def improve(*, store: SkillStore, chain: FallbackChain, generate: Generate, evaluate: Evaluate, score: Score,
            mutants: list[Mutant], seed_rules: list[str] | None = None, max_iters: int = MAX_ITERS,
            min_gain: float = MIN_GAIN) -> LoopResult:
    cur = store.current()
    if cur is None:
        rules = list(seed_rules or [])
        result = evaluate(generate(rules), mutants)
        cur = SkillVersion(version=0, rules=rules, scores=score(result), decision="baseline")
        store.save(cur)
        last = result
    else:
        last = evaluate(generate(cur.rules), mutants)
    misses = 0
    for _ in range(max_iters):
        survivors = [m for m in last.mutants if m.split == "train" and m.killed is False]  # never held-out
        if not survivors or misses >= PLATEAU:
            break
        n = store.next_version()
        try:
            rule = propose_rule(chain, cur.rules, survivors)
        except (BadRule, StepFailed) as e:
            store.save(SkillVersion(version=n, parent=cur.version, rules=cur.rules, decision="rolled_back",
                                    reason=f"reflection failed: {e}"[:300]))
            misses += 1
            continue
        rules = [*cur.rules, rule]
        result = evaluate(generate(rules), mutants)
        cand_scores = score(result)
        adopt, reason = decide(cur.scores, cand_scores, min_gain)
        cand = SkillVersion(version=n, parent=cur.version, rules=rules, diff=diff_rules(cur.rules, rules),
                            scores=cand_scores, decision="adopted" if adopt else "rolled_back", reason=reason)
        store.save(cand)
        if adopt:
            cur, last, misses = cand, result, 0
        else:
            misses += 1
    return LoopResult(final=cur, timeline=store.timeline())
