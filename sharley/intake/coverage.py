"""Coverage check: every input sentence maps to a requirement or is ignored with a reason."""
from pydantic import BaseModel, Field

from sharley.harness import FallbackChain, Step
from sharley.intake.text import contains, sentences
from sharley.schemas.spec import IgnoredSpan, Requirement


class Item(BaseModel):
    index: int
    text: str


class CoverageIn(BaseModel):
    uncovered: list[Item]
    requirements: list[dict[str, str]]


class Mapping(BaseModel):
    index: int
    requirement_ids: list[str] = Field(default_factory=list)
    ignored_reason: str | None = None


class CoverageOut(BaseModel):
    mappings: list[Mapping]


CHECK = Step("coverage_check", "For each uncovered input sentence, say which requirement ids already express it, "
             "or give an ignored_reason (e.g. greeting, repeated, not a requirement). Do not invent ids.",
             CoverageIn, CoverageOut, tier="fast")


def check_coverage(chain: FallbackChain, source: str, reqs: list[Requirement]) -> tuple[float, list[IgnoredSpan]]:
    sents = sentences(source)
    if not sents:
        return 100.0, []
    spans = [r.evidence.source_span for r in reqs if r.evidence.source_span]
    uncovered = [Item(index=i, text=s) for i, s in enumerate(sents) if not any(contains(s, sp) or contains(sp, s) for sp in spans)]
    handled, ignored = len(sents) - len(uncovered), []
    if uncovered:
        out = CHECK.run(chain, CoverageIn(uncovered=uncovered, requirements=[{"id": r.id, "text": r.text} for r in reqs]))
        known = {r.id for r in reqs}
        for m in out.mappings:
            if not 0 <= m.index < len(sents) or m.index not in {u.index for u in uncovered}:
                continue  # hallucinated index
            if any(i in known for i in m.requirement_ids):
                handled += 1
            elif m.ignored_reason and m.ignored_reason.strip():
                handled += 1
                ignored.append(IgnoredSpan(span=sents[m.index], reason=m.ignored_reason.strip()))
    return round(100.0 * handled / len(sents), 1), ignored
