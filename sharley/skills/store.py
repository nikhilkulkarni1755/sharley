"""Versioned skill store: every version, its diff, scores and accept/reject decision, with parent lineage."""
import difflib

from sharley.schemas import SkillVersion
from sharley.storage.repository import Repository


def diff_rules(old: list[str], new: list[str]) -> str:
    return "\n".join(difflib.unified_diff(old, new, "parent", "candidate", lineterm="", n=0))


class SkillStore:
    def __init__(self, repo: Repository):
        self.repo = repo

    def save(self, v: SkillVersion) -> None:
        self.repo.put("skill_versions", f"v{v.version}", v.model_dump())

    def timeline(self) -> list[SkillVersion]:
        return sorted((SkillVersion.model_validate(d) for d in self.repo.find("skill_versions")), key=lambda v: v.version)

    def current(self) -> SkillVersion | None:
        """Latest version that was adopted (or the baseline). Rolled-back versions never become current."""
        live = [v for v in self.timeline() if v.decision in ("baseline", "adopted")]
        return live[-1] if live else None

    def next_version(self) -> int:
        t = self.timeline()
        return t[-1].version + 1 if t else 0
