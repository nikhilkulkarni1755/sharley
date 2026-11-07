from sharley.runner.base import RunReport


def false_failure_rate(reference: RunReport) -> float:
    """Share of tests that fail on the CORRECT app (bad tests). A reference that will not boot counts as 1.0."""
    if not reference.boot_ok or reference.timed_out or not reference.results:
        return 1.0
    return sum(not r.passed for r in reference.results) / len(reference.results)
