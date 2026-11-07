"""Plain-English rendering of verdicts for terminals and CI."""
from sharley.schemas import Verdict

PASS_ICON = "PASS"


def render(v: Verdict) -> str:
    lines = [f"Sharley verdict: {v.status}", v.summary() if v.status == "Wrong Answer" else ""]
    if v.status not in ("Accepted",) and v.hint and v.status != "Wrong Answer":
        lines.append(f"Reason: {v.hint}")
    lines.append(f"Example tests: {v.example_passed}/{v.example_total} passed (sealed: {v.total_sealed})")
    lines.append(f"Implementer: {v.implementer.model} ({v.implementer.family}); verifier: {v.verifier.model} "
                 f"({v.verifier.family}); seed {v.seed}; spec {v.spec_hash[:12]}")
    return "\n".join(l for l in lines if l)


def exit_code(v: Verdict) -> int:
    return 0 if v.status == "Accepted" else 1


def github_annotation(v: Verdict) -> str:
    """One-line GitHub Actions error so the failing check explains itself."""
    return "" if v.status == "Accepted" else f"::error title=Sharley {v.status}::{v.summary() if v.status == 'Wrong Answer' else v.hint or v.status}"
