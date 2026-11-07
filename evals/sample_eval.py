"""Detection and false-failure check on a sample backend: tests written from the spec alone must fail on the flawed app
for the planted flaw, and must all pass on its fixed twin."""
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from evals.sample_backends import fixed_copy, flaw_ids, flawed_copy, register, spec_text
from sharley.gate import service
from sharley.gate.context import Context
from sharley.intake import IntakeInput, build_spec
from sharley.intake.files import load_codebase
from sharley.runner.base import RunReport, Sandbox
from sharley.schemas import Spec, TestCase

# keywords that tie a failing test's requirement text to a planted flaw (matched case-insensitively)
KEYWORDS = {"FLAW-LOGIC": ("refund",), "FLAW-CVE": ("token", "unsigned", "tamper", "signed"),
            "FLAW-FREE-POWER": ("billed", "zero", "tariff", "charge")}


@dataclass
class SampleResult:
    name: str
    spec: Spec
    tests: list[TestCase]
    flawed: RunReport
    fixed: RunReport
    detected: dict[str, list[str]] = field(default_factory=dict)  # flaw id -> ids of tests that caught it
    false_failures: list[str] = field(default_factory=list)  # tests failing on the FIXED twin
    differential: list[str] = field(default_factory=list)  # tests failing on flawed but passing on fixed
    bank_key: str = ""


def failed(report: RunReport) -> set[str]:
    return {r.test_id for r in report.results if not r.passed} if report.boot_ok else {"__boot__"}


def classify(spec: Spec, tests: list[TestCase], flawed: RunReport, fixed: RunReport, flaw_list: list[str]) -> SampleResult:
    bad_fixed, bad_flawed = failed(fixed), failed(flawed)
    diff = sorted(bad_flawed - bad_fixed)
    by_id = {t.id: t for t in tests}
    detected: dict[str, list[str]] = {}
    for fid in flaw_list:
        for tid in diff:
            text = " ".join(spec.get(r).text.lower() for r in by_id[tid].requirement_ids if tid in by_id)
            if any(k in text for k in KEYWORDS.get(fid, ())):
                detected.setdefault(fid, []).append(tid)
    return SampleResult("", spec, tests, flawed, fixed, detected, sorted(bad_fixed), diff)


def run_sample(name: str, ctx: Context, sandbox: Sandbox, *, seed: int = 0, workers: int = 4, home: Path | None = None) -> SampleResult:
    with tempfile.TemporaryDirectory(prefix="sharley-sample-") as tmp:
        tmp = Path(tmp)
        flawed_dir, fixed_dir = flawed_copy(name, tmp / "flawed"), fixed_copy(name, tmp / "fixed")
        spec = build_spec(ctx.verifier, IntakeInput(text=spec_text(name)), repo=ctx.repo)
        bank = service.make_bank(spec, ctx.repo, ctx.verifier, stack="docker-api", files=load_codebase(flawed_dir),
                                 seed=seed, workers=workers, allow_partial=True)
        flawed, fixed = (sandbox.run(d, bank.tests, "docker-api") for d in (flawed_dir, fixed_dir))
    result = classify(spec, bank.tests, flawed, fixed, flaw_ids(name))
    result.name, result.bank_key = name, f"{bank.spec_hash}:{bank.seed}"
    if home is not None:
        register(home, name, result.bank_key)
    return result
