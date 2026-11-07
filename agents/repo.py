"""Fetch a submitted GitHub repo safely: https github.com URLs only, shallow clone, no prompts."""
import re
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

URL = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}?(\.git)?/?$")
BRANCH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]{0,99}$")


class BadRepo(ValueError):
    pass


def validate(url: str, branch: str = "") -> tuple[str, str]:
    url = url.strip().rstrip("/")
    if not URL.match(url):
        raise BadRepo("only public https://github.com/<owner>/<repo> URLs are accepted")
    if branch and (not BRANCH.match(branch) or ".." in branch):
        raise BadRepo("invalid branch name")
    return url, branch


def git_clone(argv: list[str]) -> int:
    return subprocess.run(argv, capture_output=True, timeout=120,
                          env={"GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}).returncode


def clone(url: str, branch: str = "", run: Callable[[list[str]], int] = git_clone) -> Path:
    url, branch = validate(url, branch)
    dest = Path(tempfile.mkdtemp(prefix="sharley-repo-")) / "src"
    argv = ["git", "-c", "protocol.allow=never", "-c", "protocol.https.allow=always", "clone", "--depth", "1", "--no-tags"]
    argv += (["--branch", branch] if branch else []) + ["--", url, str(dest)]
    if run(argv) != 0:
        raise BadRepo("could not clone that repository (is it public, and does the branch exist?)")
    return dest
