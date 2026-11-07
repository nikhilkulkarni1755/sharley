"""Any input -> frozen, hashed spec.json."""
from dataclasses import dataclass

from sharley.harness import FallbackChain
from sharley.hashing import sha256_text
from sharley.intake.codebase import render_summary, summarize_codebase
from sharley.intake.coverage import check_coverage
from sharley.intake.extract import CHUNK_CHARS, propose, tag_requirements
from sharley.intake.image import describe_image
from sharley.schemas import Spec
from sharley.storage.repository import Repository

MAX_RAW_CHARS = 2_000_000


@dataclass
class IntakeInput:
    text: str | None = None
    image: bytes | None = None
    files: dict[str, str] | None = None


def normalize(inp: IntakeInput, chain: FallbackChain, *, include_raw: bool = False) -> tuple[str, str | None]:
    """Return (canonical source text, detected stack)."""
    if sum(x is not None for x in (inp.text, inp.image, inp.files)) != 1:
        raise ValueError("provide exactly one of text, image or files")
    if inp.text is not None:
        return inp.text, None
    if inp.image is not None:
        return describe_image(chain, inp.image), None
    summary = summarize_codebase(inp.files)
    text = render_summary(summary)
    if include_raw:  # whole-repo pass for the long-context model
        raw = "\n\n".join(f"### {p}\n{c}" for p, c in inp.files.items())[:MAX_RAW_CHARS]
        text += "\n\n" + raw
    return text, summary.stack


def build_spec(chain: FallbackChain, inp: IntakeInput, *, long_chain: FallbackChain | None = None,
               repo: Repository | None = None, chunk_chars: int = CHUNK_CHARS) -> Spec:
    source, stack = normalize(inp, chain, include_raw=long_chain is not None)
    raw = propose(chain, source, stack, long_chain=long_chain, chunk_chars=chunk_chars)
    reqs, assumptions = tag_requirements(raw, source)
    coverage, ignored = check_coverage(chain, source, reqs)
    spec = Spec(stack=stack, source_hash=sha256_text(source), requirements=reqs, assumptions=assumptions,
                ignored=ignored, coverage_pct=coverage)
    if repo is not None:
        version = len(repo.find("specs", source_hash=spec.source_hash)) + 1
        spec = spec.model_copy(update={"version": version})
        repo.put("specs", spec.spec_hash, spec.model_dump())
    return spec
