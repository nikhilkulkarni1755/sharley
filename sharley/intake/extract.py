"""Requirement extraction: LLM proposes, plain code assigns IDs and verifies evidence."""
from pydantic import BaseModel, Field

from sharley.harness import FallbackChain, Step
from sharley.intake.text import contains, norm
from sharley.schemas.spec import Category, Evidence, Requirement, StackName

CHUNK_CHARS = 12_000


class RawRequirement(BaseModel):
    text: str = Field(min_length=3)
    category: Category
    source_span: str | None = None
    assumption: str | None = None


class ExtractIn(BaseModel):
    text: str
    stack: StackName | None = None


class ExtractOut(BaseModel):
    requirements: list[RawRequirement] = Field(min_length=1)


EXTRACT = Step("extract_requirements",
               "Extract atomic, testable requirements from the input. For each: text, category "
               "(functional|security|deployment|data), and EITHER source_span (an exact quote from the input) "
               "OR assumption (why you inferred it). Include security requirements implied by the feature "
               "(auth, ownership, input validation) as inferred. One behaviour per requirement.",
               ExtractIn, ExtractOut, tier="strong")


def chunks(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Split on line boundaries so no chunk exceeds size (single huge lines are hard-split)."""
    out, cur = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > size:
            if cur:
                out.append(cur)
                cur = ""
            out.append(line[:size])
            line = line[size:]
        if len(cur) + len(line) > size:
            out.append(cur)
            cur = ""
        cur += line
    if cur.strip():
        out.append(cur)
    return out


def propose(chain: FallbackChain, text: str, stack: StackName | None, *, long_chain: FallbackChain | None = None,
            chunk_chars: int = CHUNK_CHARS) -> list[RawRequirement]:
    if not text.strip():
        raise ValueError("empty input")
    if len(text) > chunk_chars and long_chain is not None:
        try:  # whole input in one pass on the long-context model
            return EXTRACT.run(long_chain, ExtractIn(text=text, stack=stack)).requirements
        except Exception:
            pass  # fall through to chunked extraction so nothing is truncated
    parts = chunks(text, chunk_chars) if len(text) > chunk_chars else [text]
    seen, out = set(), []
    for part in parts:
        for r in EXTRACT.run(chain, ExtractIn(text=part, stack=stack)).requirements:
            if norm(r.text) not in seen:
                seen.add(norm(r.text))
                out.append(r)
    return out


def tag_requirements(raw: list[RawRequirement], source: str) -> tuple[list[Requirement], dict[str, str]]:
    """Assign R/A ids. Observed only if the quoted span really appears in the input; else inferred."""
    reqs, assumptions, by_text = [], {}, {}
    for i, r in enumerate(raw, 1):
        if r.source_span and contains(source, r.source_span):
            ev = Evidence(kind="observed", source_span=r.source_span.strip())
        else:
            note = r.assumption or ("Quoted evidence not found in input; treated as an assumption"
                                    if r.source_span else "Assumed from context")
            aid = by_text.setdefault(norm(note), f"A{len(by_text) + 1}")
            assumptions[aid] = note
            ev = Evidence(kind="inferred", assumption_id=aid)
        reqs.append(Requirement(id=f"R{i}", text=r.text.strip(), category=r.category, evidence=ev))
    return reqs, assumptions
