"""Reflection: from TRAIN survivors only, propose one new rule for the test writers."""
from pydantic import BaseModel, Field

from sharley.harness import FallbackChain, Step
from sharley.schemas import Mutant

MAX_RULES = 20
MAX_RULE_CHARS = 300


class Survivor(BaseModel):
    operator: str
    category: str
    file: str
    original: str
    mutated: str


class ReflectIn(BaseModel):
    rules: list[str]
    survivors: list[Survivor]


class ReflectOut(BaseModel):
    rule: str = Field(min_length=10)
    rationale: str = ""


REFLECT = Step("reflect_on_survivors",
               "These code mutations were NOT detected by the current tests. Propose ONE general testing rule "
               "(an instruction to a test writer, one sentence) that would make tests catch this class of bug on "
               "any resource or endpoint. Do not mention file names, line numbers or copy code.",
               ReflectIn, ReflectOut, tier="strong")


class BadRule(ValueError):
    pass


def validate_rule(rule: str, existing: list[str], survivors: list[Mutant]) -> str:
    rule = " ".join(rule.split())
    if not rule or len(rule) > MAX_RULE_CHARS:
        raise BadRule("rule must be one short sentence")
    if "<input>" in rule or "```" in rule or "ignore" in rule.lower() and "instruction" in rule.lower():
        raise BadRule("rule contains prompt-control text")
    if rule.lower() in {r.lower() for r in existing}:
        raise BadRule("duplicate rule")
    if len(existing) >= MAX_RULES:
        raise BadRule("rule limit reached")
    if any(m.mutated.strip() and m.mutated.strip() in rule for m in survivors):
        raise BadRule("rule copies a mutant's code (overfitting)")
    return rule


def propose_rule(chain: FallbackChain, rules: list[str], survivors: list[Mutant]) -> str:
    if any(m.split != "train" for m in survivors):
        raise ValueError("reflection may only see train mutants")
    out = REFLECT.run(chain, ReflectIn(rules=rules, survivors=[
        Survivor(operator=m.operator, category=m.category, file=m.file, original=m.original.strip(),
                 mutated=m.mutated.strip()) for m in survivors[:12]]))
    return validate_rule(out.rule, rules, survivors)
