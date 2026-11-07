"""Path fidelity: do the generated tests only call routes the application really has?"""
import re
from dataclasses import dataclass, field

from sharley.schemas import TestCase

_LITERAL = re.compile(r"""['"](/[A-Za-z0-9_\-./{}<>:$]*)(?:\?[^'"]*)?['"]""")
_PARAM = re.compile(r"\{[^}]*\}|<[^>]*>|:\w+")


def _route_regex(route: str) -> re.Pattern:
    path = route.split(" ", 1)[-1].rstrip("/") or "/"
    return re.compile("^" + "/".join("[^/]+" if _PARAM.fullmatch(seg) else re.escape(seg) for seg in path.split("/")) + "/?$")


@dataclass
class Fidelity:
    used: int = 0
    matched: int = 0
    unknown: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.matched / self.used if self.used else 1.0


def path_fidelity(tests: list[TestCase], routes: list[str]) -> Fidelity:
    """Share of distinct path literals in the tests that match a real route (verb-insensitive).

    Greenfield specs have no routes, so there is nothing to check (callers should skip them).
    """
    patterns = [_route_regex(r) for r in routes]
    seen: dict[str, bool] = {}
    for t in tests:
        for m in _LITERAL.finditer(t.code):
            path = _PARAM.sub("X", m.group(1)).split("?")[0].rstrip("/") or "/"
            if path not in seen:
                seen[path] = any(p.match(path) for p in patterns)
    return Fidelity(used=len(seen), matched=sum(seen.values()), unknown=sorted(p for p, ok in seen.items() if not ok))
