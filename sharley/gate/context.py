"""Wire configuration (environment) into concrete collaborators."""
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from sharley.harness import FallbackChain
from sharley.providers import long_context_chain, verifier_chain
from sharley.runner import DockerSandbox
from sharley.runner.base import Sandbox
from sharley.storage import open_repository
from sharley.storage.repository import Repository


def read_dotenv(path: Path) -> dict[str, str]:
    """KEY=VALUE lines only; comments, blanks and empty values are skipped so a template never blanks a real value."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("\"'")
        if sep and key.isidentifier() and not line.lstrip().startswith("#") and value:
            out[key] = value
    return out


def load_env(environ: Mapping[str, str] = os.environ, dotenv: Path = Path(".env")) -> dict[str, str]:
    """Real environment variables always win over .env."""
    return {**read_dotenv(dotenv), **environ}


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
