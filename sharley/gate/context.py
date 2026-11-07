"""Wire configuration (environment) into concrete collaborators."""
from collections.abc import Mapping
from dataclasses import dataclass

from sharley.harness import FallbackChain
from sharley.providers import long_context_chain, verifier_chain
from sharley.runner import DockerSandbox
from sharley.runner.base import Sandbox
from sharley.storage import open_repository
from sharley.storage.repository import Repository


@dataclass
class Context:
    env: Mapping[str, str]
    repo: Repository
    verifier: FallbackChain
    long_context: FallbackChain
    sandbox: Sandbox

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Context":
        verifier, long_ctx = verifier_chain(env), long_context_chain(env)
        verifier.check()
        long_ctx.check()
        return cls(env=env, repo=open_repository(env), verifier=verifier, long_context=long_ctx, sandbox=DockerSandbox())
