from evals.sample_eval import classify, failed
from sharley.runner.base import RunReport, TestResult
from sharley.schemas import Evidence, Requirement, Spec, TestCase

EV = Evidence(kind="observed", source_span="x")
SPEC = Spec(source_hash="s", requirements=[
    Requirement(id="R1", text="A payment can be refunded only once", category="security", evidence=EV),
    Requirement(id="R2", text="Unsigned or tampered tokens must be rejected", category="security", evidence=EV),
    Requirement(id="R3", text="GET /health returns 200", category="deployment", evidence=EV)])


def t(i, req):
    return TestCase(id=f"T{i}", requirement_ids=[req], name="n", family="functional", file=f"tests/t{i}.py", code="x")


def rep(*failing, n=3, boot=True):
    return RunReport(boot_ok=boot, results=[TestResult(test_id=f"T{i}", passed=f"T{i}" not in failing,
                                                      kind="pass" if f"T{i}" not in failing else "assert") for i in range(1, n + 1)])


TESTS = [t(1, "R1"), t(2, "R2"), t(3, "R3")]


def test_detection_is_the_difference_between_flawed_and_fixed():
    r = classify(SPEC, TESTS, rep("T1", "T2"), rep(), ["FLAW-LOGIC", "FLAW-CVE"])
    assert r.detected == {"FLAW-LOGIC": ["T1"], "FLAW-CVE": ["T2"]} and r.false_failures == [] and r.differential == ["T1", "T2"]


def test_a_test_failing_on_both_is_a_false_failure_not_a_detection():
    r = classify(SPEC, TESTS, rep("T1", "T3"), rep("T3"), ["FLAW-LOGIC"])
    assert r.detected == {"FLAW-LOGIC": ["T1"]} and r.false_failures == ["T3"] and r.differential == ["T1"]


def test_missed_flaw_is_reported_as_absent():
    assert classify(SPEC, TESTS, rep(), rep(), ["FLAW-LOGIC", "FLAW-CVE"]).detected == {}


def test_unrelated_differential_failures_do_not_count_as_detections():
    assert classify(SPEC, TESTS, rep("T3"), rep(), ["FLAW-LOGIC"]).detected == {}


def test_boot_failure_is_never_mistaken_for_a_clean_run():
    assert failed(RunReport(boot_ok=False)) == {"__boot__"}
    r = classify(SPEC, TESTS, rep(), RunReport(boot_ok=False), ["FLAW-LOGIC"])
    assert r.false_failures == ["__boot__"]


def _bank():
    from sharley.schemas import TestBank
    tests = [t(1, "R1").model_copy(update={"visibility": "example"}), t(2, "R2").model_copy(update={"visibility": "sealed"}),
             t(3, "R3").model_copy(update={"visibility": "sealed"})]
    return TestBank(spec_hash="h", seed=0, tests=tests)


def test_calibration_drops_tests_that_fail_on_the_correct_reference():
    from evals.sample_eval import calibrate
    bank, dropped = calibrate(_bank(), rep("T3"))
    assert dropped == ["T3"] and [x.id for x in bank.tests] == ["T1", "T2"]


def test_calibration_refuses_when_the_reference_does_not_boot_or_nothing_sealed_would_remain():
    import pytest
    from evals.sample_eval import calibrate
    with pytest.raises(ValueError, match="did not boot"):
        calibrate(_bank(), RunReport(boot_ok=False))
    with pytest.raises(ValueError, match="no sealed"):
        calibrate(_bank(), rep("T2", "T3"))


def test_calibration_keeps_everything_when_the_reference_passes():
    from evals.sample_eval import calibrate
    bank, dropped = calibrate(_bank(), rep())
    assert dropped == [] and len(bank.tests) == 3


def test_detectors_are_sealed_so_examples_cannot_hide_the_flaw():
    from evals.sample_eval import calibrate
    bank = _bank()
    bank = bank.model_copy(update={"tests": [bank.tests[0].model_copy(update={"visibility": "example"}),
                                             bank.tests[1].model_copy(update={"visibility": "example"}), bank.tests[2]]})
    out, dropped = calibrate(bank, rep(), rep("T1", "T2"))  # T1, T2 catch the flaw (fail on flawed only)
    assert dropped == [] and [t.visibility for t in out.tests] == ["sealed", "sealed", "sealed"]


def test_a_failing_flawed_run_that_did_not_boot_does_not_seal_anything():
    from evals.sample_eval import calibrate
    out, _ = calibrate(_bank(), rep(), RunReport(boot_ok=False))
    assert [t.visibility for t in out.tests] == ["example", "sealed", "sealed"]
