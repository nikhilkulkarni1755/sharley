"""Chat logic for ASI:One (and the CLI/web fallback): spec -> requirement review -> tests -> submission -> verdict."""
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol as TypingProtocol

from agents.cards import card_text, requirements_card, verdict_card
from agents.repo import BadRepo, clone
from sharley.intake import IntakeInput
from sharley.intake.files import load_codebase
from sharley.judge import IndependenceError
from sharley.schemas import ModelRef, Spec, TestBank, Verdict

HELP = ("Send me a spec (text, or a public GitHub repo URL). I'll list the requirements for you to review, "
        "build a hidden test suite, and then judge your implementation: `submit <github-url> [branch] "
        "[model=NAME family=NAME]`.")
GITHUB = re.compile(r"https://github\.com/\S+")
KV = re.compile(r"\b(model|family)=([\w.\-]{1,60})")


class Services(TypingProtocol):
    def make_spec(self, inp: IntakeInput) -> Spec: ...
    def make_bank(self, spec: Spec) -> TestBank: ...
    def judge(self, bank: TestBank, workspace: Path, implementer: ModelRef) -> Verdict: ...


@dataclass
class Session:
    spec: Spec | None = None
    bank: TestBank | None = None


@dataclass
class Reply:
    text: str
    card: dict | None = None


@dataclass
class Conversation:
    services: Services
    fetch: Callable[[str, str], Path] = clone
    sessions: dict[str, Session] = field(default_factory=dict)

    def handle(self, session_id: str, message: str) -> Reply:
        s = self.sessions.setdefault(session_id, Session())
        text = message.strip()
        low = text.lower()
        try:
            if not text or low in ("help", "?"):
                return Reply(HELP)
            if low.startswith("submit"):
                return self._submit(s, text)
            if low in ("approve", "yes", "generate tests", "generate") and s.spec:
                return self._bank(s)
            return self._intake(s, text)
        except BadRepo as e:
            return Reply(f"I couldn't use that repository: {e}")
        except IndependenceError as e:
            return Reply(f"Independence check failed: {e}. Tell me a different `family=` for your implementer.")
        except Exception as e:  # never surface a stack trace in chat; tell the user how to retry
            return Reply(f"Something failed on my side ({type(e).__name__}). Please retry the same message in a moment.")

    def _intake(self, s: Session, text: str) -> Reply:
        if len(text) < 10:
            return Reply("That's too short to turn into requirements. " + HELP)
        url = GITHUB.fullmatch(text)
        if url:
            repo = self.fetch(text, "")
            try:
                inp = IntakeInput(files=load_codebase(repo))
            finally:
                shutil.rmtree(repo.parent, ignore_errors=True)
        else:
            inp = IntakeInput(text=text)
        s.spec, s.bank = self.services.make_spec(inp), None
        card = requirements_card(s.spec)
        return Reply(card_text(card), card)

    def _bank(self, s: Session) -> Reply:
        s.bank = self.services.make_bank(s.spec)
        examples = "\n\n".join(f"`{t.file}`\n```\n{t.code}\n```" for t in s.bank.examples)
        return Reply(f"Built {len(s.bank.tests)} tests: {len(s.bank.examples)} examples you may see, "
                     f"{len(s.bank.sealed)} sealed (hidden). Add these example tests to your repo unchanged, "
                     "implement until they pass, push to a public GitHub repo, then send "
                     f"`submit <github-url> [branch] model=NAME family=NAME`.\n\n{examples}")

    def _submit(self, s: Session, text: str) -> Reply:
        if s.bank is None:
            return Reply("There's nothing to judge against yet. Send a spec and `approve` first.")
        parts = KV.sub("", text).split()[1:]
        if not parts:
            return Reply("Usage: `submit <github-url> [branch] [model=NAME family=NAME]`")
        kv = dict(KV.findall(text))
        repo = self.fetch(parts[0], parts[1] if len(parts) > 1 else "")
        try:
            v = self.services.judge(s.bank, repo, ModelRef(provider="external", model=kv.get("model", "unknown"),
                                                          family=kv.get("family", "external")))
        finally:
            shutil.rmtree(repo.parent, ignore_errors=True)
        card = verdict_card(v)
        return Reply(card_text(card), card)
