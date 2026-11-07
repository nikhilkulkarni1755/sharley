"""Precompute the stage demo: a real sealed verdict, a real mutation eval and a real adopt/rollback timeline.

HONESTY NOTE: the LLM test writer is replaced by a deterministic stand-in (skill rules unlock subsets of the
hand-written oracle suite). Mutant kills, false failures, scores, the sealed verdict and every adopt/rollback
decision are computed for real, in the Docker sandbox. Re-run with provider keys to replace the stand-in.
"""
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from evals.graders import score
from evals.reference import APP_DIR, SPEC_TEXT, oracle_tests, reference_spec
from sharley.api.runs import RecordingSandbox, result_events
from sharley.api.views import bank_view
from sharley.harness import FallbackChain
from sharley.judge import export_workspace, split_bank
from sharley.mutation import apply_mutant, evaluate, generate_mutants
from sharley.runner.base import Sandbox
from sharley.schemas import ModelRef, Mutant, TestCase
from sharley.skills import SkillStore, improve
from sharley.storage import JsonRepository
from tests.fakes import ScriptedProvider  # deterministic reflection stand-in

OUT = Path(__file__).resolve().parent / "demo.json"
BASELINE = {"r1", "r2", "r3", "r5", "r7", "r12"}
UNLOCKS = {  # skill rule -> oracle files it makes the (stand-in) test writer produce
    "Always test ownership and authentication on every resource endpoint.": {"r8", "r9"},
    "Re-send every request with different header casing.": set(),
    "Probe rate limits, error bodies and injection on every public input.": {"r4", "r10", "r11"},
    "Hammer every endpoint with random payloads and expect 400 for any invalid one.": {"flaky"},
}
FLAKY = TestCase(id="T99", requirement_ids=["R2"], name="random payload rejection", family="functional",
                 file="tests/test_flaky.py", hint="invalid payloads are not rejected",
                 code=("import os\nimport httpx\n\n\ndef test_short_password_is_400():\n"
                       "    r = httpx.post(os.environ['BASE_URL'] + '/auth/signup', json={'username': 'zz1', 'password': 'x'})\n"
                       "    assert r.status_code == 400\n"))


def tests_for(rules: list[str]) -> list[TestCase]:
    wanted = set(BASELINE).union(*(UNLOCKS[r] for r in rules))
    chosen = [t for t in oracle_tests() if t.name.split("_")[1] in wanted]
    return chosen + ([FLAKY] if "flaky" in wanted else [])


def valid_mutants(sandbox: Sandbox, seed: int, workers: int) -> list[Mutant]:
    """Drop equivalent mutants: those that even the full oracle suite cannot kill."""
    all_m = generate_mutants(APP_DIR, seed=seed)
    res = evaluate(sandbox, APP_DIR, oracle_tests(), all_m, workers=workers)
    return [m.model_copy(update={"killed": None}) for m in res.mutants if m.killed is True]


def buggy_submission(sandbox_dir: Path, seed: int) -> Path:
    bug = next(m for m in generate_mutants(APP_DIR, seed=seed) if m.operator == "missing_ownership_check")
    return apply_mutant(APP_DIR, bug, sandbox_dir / "impl")


def build_demo(sandbox: Sandbox, *, seed: int = 7, workers: int = 4) -> dict:
    spec = reference_spec()
    mutants = valid_mutants(sandbox, seed, workers)
    with tempfile.TemporaryDirectory(prefix="sharley-demo-") as tmp:
        tmp = Path(tmp)
        # --- the sealed verdict on a plausible-looking but wrong implementation
        author = ModelRef(provider="oracle", model="hand-written-suite", family="human")
        bank = split_bank(oracle_tests(), spec.spec_hash, seed).model_copy(update={"author": author})
        impl = buggy_submission(tmp, seed)
        shutil.copytree(impl, tmp / "ws")
        export_workspace(bank, tmp / "ws")
        recorder = RecordingSandbox(sandbox)
        from sharley.gate.service import check_submission
        verdict = check_submission(bank, tmp / "ws", recorder, "docker-api",
                                   ModelRef(provider="gemini", model="gemini-4-argon", family="google"))
        events = result_events(bank, recorder.last, verdict, [])
        # --- the evaluation of the final suite and the self-improvement timeline
        store = SkillStore(JsonRepository(tmp / "skills"))
        replies = [json.dumps({"rule": r, "rationale": "stand-in"}) for r in UNLOCKS]
        chain = FallbackChain([ScriptedProvider("stand-in", replies)])
        ev = lambda tests, ms: evaluate(sandbox, APP_DIR, tests, ms, workers=workers)  # noqa: E731
        result = improve(store=store, chain=chain, generate=tests_for, evaluate=ev, score=lambda r: score(r),
                         mutants=mutants, max_iters=len(UNLOCKS))
        final = evaluate(sandbox, APP_DIR, tests_for(result.final.rules), mutants, workers=workers)
    return {
        "meta": {"source": "oracle-stand-in", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "note": __doc__.split("HONESTY NOTE: ")[1].strip().replace("\n", " ")},
        "spec": spec.model_dump(), "spec_text": SPEC_TEXT,
        "bank": bank_view(bank), "events": events,
        "eval": {"mutants": [{"id": m.id, "operator": m.operator, "category": m.category, "split": m.split, "killed": m.killed}
                             for m in final.mutants],
                 "reference": {"tests": len(final.reference.results), "failed": sum(not r.passed for r in final.reference.results)},
                 "scores": score(final).model_dump()},
        "timeline": [v.model_dump() for v in result.timeline],
    }


def main(sandbox: Sandbox | None = None, out: Path = OUT) -> Path:
    from sharley.runner import DockerSandbox

    out.write_text(json.dumps(build_demo(sandbox or DockerSandbox()), indent=2))
    return out
