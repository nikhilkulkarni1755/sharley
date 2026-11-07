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
from sharley.schemas import Spec, TestBank, TestCase

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


def calibrate(bank: TestBank, reference: RunReport, flawed: RunReport | None = None) -> tuple[TestBank, list[str]]:
    """Drop every test that fails on the known-correct reference (such a test is wrong, not the implementation).

    With the flawed run too, tests that catch the known flaw (fail on flawed, pass on reference) are sealed, so a
    playground submission cannot pass just because the detecting tests happened to be shown as examples."""
    if not reference.boot_ok:
        raise ValueError("the reference implementation did not boot; refusing to calibrate")
    bad = failed(reference)
    detectors = failed(flawed) - bad if flawed is not None and flawed.boot_ok else set()
    kept = [t.model_copy(update={"visibility": "sealed"}) if t.id in detectors else t for t in bank.tests if t.id not in bad]
    if not any(t.visibility == "sealed" for t in kept):
        raise ValueError("calibration would leave no sealed tests")
    return bank.model_copy(update={"tests": kept}), sorted(bad)


def calibrate_sample(name: str, ctx: Context, sandbox: Sandbox, home: Path) -> tuple[int, int, list[str]]:
    """Calibrate the registered bank of a sample backend against its fixed twin (and seal the flaw detectors). Returns (before, after, dropped)."""
    from sharley.judge import load_bank, save_bank

    from evals.sample_backends import load_index

    bank = load_bank(ctx.repo, load_index(home)[name])
    with tempfile.TemporaryDirectory(prefix="sharley-cal-") as tmp:
        fixed = sandbox.run(fixed_copy(name, Path(tmp) / "fixed"), bank.tests, "docker-api")
        flawed = sandbox.run(flawed_copy(name, Path(tmp) / "flawed"), bank.tests, "docker-api")
    calibrated, dropped = calibrate(bank, fixed, flawed)
    save_bank(ctx.repo, calibrated)
    return len(bank.tests), len(calibrated.tests), dropped
