"""Parse test-runner output into per-test-case results. Only trusted runner sections are read."""
import json
import re

from sharley.runner.base import TestResult
from sharley.schemas.testbank import TestCase

_MARK = "short test summary info"
CLIP = 600


def _by_file(tests: list[TestCase]) -> dict[str, TestCase]:
    return {t.file: t for t in tests}


def failures(entries: list[tuple[str, str]]):
    return [(h, r) for h, r in entries if h != "PASSED"]


def _is_runtime(head: str, rest: str) -> bool:
    """ERROR (setup/collection) and non-assertion exceptions are runtime errors; a bare FAILED is an assertion."""
    msg = rest.partition(" - ")[2]
    if head == "ERROR":
        return True
    return bool(re.match(r"[\w.]+(Error|Exception|Timeout|Exit)\b", msg)) and not msg.startswith("AssertionError")


def parse_pytest(stdout: str, tests: list[TestCase]) -> list[TestResult]:
    """Read only the '-rA' summary block, so app/test prints can't forge PASSED lines."""
    section = stdout.split(_MARK, 1)[1] if _MARK in stdout else ""
    status: dict[str, list[tuple[str, str]]] = {}
    for line in section.splitlines():
        head, _, rest = line.partition(" ")
        if head in ("PASSED", "FAILED", "ERROR") and "::" in rest:
            path = rest.split("::", 1)[0].strip().lstrip("./")
            status.setdefault(path, []).append((head, rest))
    out = []
    for t in tests:
        entries = status.get(t.file, [])
        bad = [r for h, r in entries if h != "PASSED"]
        if entries and not bad:
            out.append(TestResult(test_id=t.id, passed=True, kind="pass"))
        elif bad:
            kind = "runtime" if any(_is_runtime(h, r) for h, r in failures(entries)) else "assert"
            out.append(TestResult(test_id=t.id, passed=False, kind=kind, output=bad[0][:CLIP]))
        else:
            out.append(TestResult(test_id=t.id, passed=False, kind="runtime", output="test was not collected or run"))
    return out


def parse_vitest(stdout: str, tests: list[TestCase]) -> list[TestResult]:
    start = stdout.find('{"numTotalTestSuites"')
    try:
        data = json.JSONDecoder().raw_decode(stdout[start:])[0] if start >= 0 else {}
    except ValueError:
        data = {}
    files = {}
    for suite in data.get("testResults", []):
        name = suite.get("name", "")
        files[name] = suite
    out = []
    for t in tests:
        suite = next((s for n, s in files.items() if n.endswith("/" + t.file) or n == t.file), None)
        if suite is None:
            out.append(TestResult(test_id=t.id, passed=False, kind="runtime", output="test was not collected or run"))
        elif suite.get("status") == "passed":
            out.append(TestResult(test_id=t.id, passed=True, kind="pass"))
        else:
            msgs = " ".join(m for a in suite.get("assertionResults", []) for m in a.get("failureMessages", []))
            kind = "assert" if "AssertionError" in msgs or "expected" in msgs else "runtime"
            out.append(TestResult(test_id=t.id, passed=False, kind=kind, output=(msgs or suite.get("message", ""))[:CLIP]))
    return out
