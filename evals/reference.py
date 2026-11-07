"""The reference notes app: its spec, hand-written oracle tests, and paths."""
import re
from pathlib import Path

from sharley.hashing import sha256_text
from sharley.intake.text import contains
from sharley.schemas import Evidence, Requirement, Spec, TestCase

ROOT = Path(__file__).resolve().parent / "reference_apps" / "notes"
APP_DIR = ROOT  # contains app/ ; run with: uvicorn app.main:app
SPEC_TEXT = (ROOT / "SPEC.md").read_text()

# id, category, requirement text, exact quote from SPEC.md
_REQS = [
    ("R1", "functional", "A username is 3-32 letters, digits or underscore and unique", "a username (3-32 letters, digits or underscore)"),
    ("R2", "functional", "A password must be at least 8 characters", "a password of at least 8 characters"),
    ("R3", "functional", "Logging in with the right password returns a token; a wrong one is rejected", "Wrong passwords are rejected"),
    ("R4", "security", "After 5 failed logins in a minute the account is locked out", "after 5 failed logins in a minute the account is locked out"),
    ("R5", "functional", "A note has a title of 1-100 characters and an optional body up to 10000 characters", "a title (1-100 chars) and an optional body (up to 10000 chars)"),
    ("R6", "functional", "Users can list, search by title and page through their notes (default 20, max 100)", "list their notes, search by title, and page through them (default 20, max 100 per page)"),
    ("R7", "functional", "Users can read, edit and delete a note by id", "read, edit and delete a note by id"),
    ("R8", "security", "Each user can only see and change their own notes", "Each user must only ever see and change their own notes"),
    ("R9", "security", "Everything except signup, login and health requires a valid token", "Everything except signup, login and the health check needs a valid token"),
    ("R10", "security", "Errors must not expose internals such as stack traces", "Errors must not expose internals like stack traces"),
    ("R11", "security", "User input must never be able to alter database queries", None),
    ("R12", "deployment", "GET /health returns 200 when the service is running", "GET /health returning 200 when it is running"),
]


def reference_spec() -> Spec:
    reqs, assumptions = [], {}
    for rid, cat, text, quote in _REQS:
        if quote and contains(SPEC_TEXT, quote):
            ev = Evidence(kind="observed", source_span=quote)
        else:  # not stated in the text: an explicit assumption, never silently observed
            assumptions["A1"] = "Any SQL-backed service must be safe from injection"
            ev = Evidence(kind="inferred", assumption_id="A1")
        reqs.append(Requirement(id=rid, text=text, category=cat, evidence=ev))
    return Spec(stack="docker-api", source_hash=sha256_text(SPEC_TEXT), requirements=reqs,
                assumptions=assumptions, coverage_pct=100.0)


def oracle_tests() -> list[TestCase]:
    """The hand-written suite, as TestCases (also the offline fixture bank)."""
    out = []
    for i, path in enumerate(sorted((ROOT / "oracle").glob("test_*.py")), 1):
        code = path.read_text()
        reqs = re.search(r"# reqs: (.+)", code).group(1).split(",")
        hint = re.search(r"# hint: (.+)", code).group(1)
        family = "security" if any(r.strip() in {"R4", "R8", "R9", "R10", "R11"} for r in reqs) else "functional"
        if reqs == ["R12"]:
            family = "env"
        out.append(TestCase(id=f"T{i}", requirement_ids=[r.strip() for r in reqs], name=path.stem, family=family,
                            file=f"tests/{path.name}", code=code, hint=hint))
    return out
