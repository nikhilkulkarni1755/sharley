"""Adapter from the chat logic to the Sharley service layer."""
from pathlib import Path

from sharley.gate import service
from sharley.gate.context import Context
from sharley.intake import IntakeInput, build_spec
from sharley.schemas import ModelRef, Spec, TestBank, Verdict


class LocalServices:
    def __init__(self, ctx: Context):
        self.ctx = ctx

    def make_spec(self, inp: IntakeInput) -> Spec:
        return build_spec(self.ctx.verifier, inp, repo=self.ctx.repo)

    def make_bank(self, spec: Spec) -> TestBank:
        return service.make_bank(spec, self.ctx.repo, self.ctx.verifier, stack=spec.stack or "docker-api")

    def judge(self, bank: TestBank, workspace: Path, implementer: ModelRef) -> Verdict:
        return service.check_submission(bank, workspace, self.ctx.sandbox, "docker-api", implementer, repo=self.ctx.repo)
