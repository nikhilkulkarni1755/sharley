"""Versioned skill store: every version, its diff, scores and accept/reject decision, with parent lineage."""
import difflib

from sharley.schemas import SkillVersion
from sharley.storage.repository import Repository


def diff_rules(old: list[str], new: list[str]) -> str:
    return "\n".join(difflib.unified_diff(old, new, "parent", "candidate", lineterm="", n=0))


GLOBAL = "global"


class SkillStore:
    """Versioned skills per scope: "global" is shared by everyone; any other scope (an org or user id) is a private
    overlay that is only ever applied on top of the global rules for that scope."""

    def __init__(self, repo: Repository, scope: str = GLOBAL):
        if not scope.replace("-", "").replace("_", "").isalnum():
            raise ValueError("scope must be alphanumeric")
        self.repo, self.scope = repo, scope

    def save(self, v: SkillVersion) -> None:
        self.repo.put("skill_versions", f"{self.scope}:v{v.version}", {**v.model_dump(), "scope": self.scope})

    def timeline(self) -> list[SkillVersion]:
        docs = self.repo.find("skill_versions", scope=self.scope)
        return sorted((SkillVersion.model_validate({k: x for k, x in d.items() if k != "scope"}) for d in docs),
                      key=lambda v: v.version)

    def current(self) -> SkillVersion | None:
        """Latest version that was adopted (or the baseline). Rolled-back versions never become current."""
        live = [v for v in self.timeline() if v.decision in ("baseline", "adopted")]
        return live[-1] if live else None

    def next_version(self) -> int:
        t = self.timeline()
        return t[-1].version + 1 if t else 0

    def active_rules(self) -> list[str]:
        """Global adopted rules first, then this scope's own adopted rules (deduplicated, order kept)."""
        mine = self.current()
        base = SkillStore(self.repo, GLOBAL).current() if self.scope != GLOBAL else None
        rules = [*(base.rules if base else []), *(mine.rules if mine else [])]
        return list(dict.fromkeys(rules))
