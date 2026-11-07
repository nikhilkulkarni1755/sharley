"""Local Docker sandbox: no network, read-only root, dropped capabilities, resource limits."""
import io
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sharley.profiles import PROFILES
from sharley.runner.base import RunReport, Sandbox
from sharley.runner.parse import parse_pytest, parse_vitest
from sharley.schemas.spec import StackName
from sharley.schemas.testbank import TestCase

IMAGES = {"docker-api": "sharley-runner-py:latest", "nextjs": "sharley-runner-node:latest"}
IGNORE = shutil.ignore_patterns(".git", "__pycache__", "node_modules", ".venv", ".env", ".env.*", "conftest.py",
                                "pytest.ini", "tox.ini", "setup.cfg", "vitest.config.*", "playwright.config.*")
BOOT_WAIT_S = 60


@dataclass
class ExecResult:
    returncode: int
    stdout: str
    stderr: str = ""
    timed_out: bool = False


Executor = Callable[[list[str], float, bytes | None], ExecResult]


def subprocess_exec(argv: list[str], timeout: float, stdin: bytes | None = None) -> ExecResult:
    try:
        p = subprocess.run(argv, capture_output=True, input=stdin, timeout=timeout)
        p.stdout, p.stderr = p.stdout.decode(errors="replace"), p.stderr.decode(errors="replace")
        return ExecResult(p.returncode, p.stdout, p.stderr)
    except subprocess.TimeoutExpired as e:
        return ExecResult(124, (e.stdout or b"").decode(errors="replace"), "", timed_out=True)
    except FileNotFoundError:
        return ExecResult(127, "", "docker not installed")


DROP = "setpriv --reuid=65534 --regid=65534 --clear-groups --no-new-privs"


DROP = "setpriv --reuid=65534 --regid=65534 --clear-groups --no-new-privs"


def run_script(stack: StackName, files: list[str]) -> str:
    """Input arrives as a tar on stdin into a root-only tmpfs (/in). The harness runs as root with no useful
    caps; the untrusted app runs as nobody, so it cannot see the tests, edit them, signal the harness, or
    write to its stdout. Results therefore cannot be forged."""
    p = PROFILES[stack]
    url = f"http://127.0.0.1:{p.port}{p.health_path}"
    probe = (f"python -c \"import urllib.request as u;u.urlopen('{url}',timeout=1)\"" if stack == "docker-api"
             else f"node -e \"fetch('{url}').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))\"")
    run_tests = ("python -m pytest -c /dev/null --rootdir=/in/t -q -rA --tb=short -p no:cacheprovider " + " ".join(files)
                 if stack == "docker-api" else "npx vitest run --reporter=json " + " ".join(files))
    return f"""tar -x --no-same-owner -C /in || exit 4
cp -r /in/work/. /app/ && chown -R 65534:65534 /app && cd /app
({DROP} env HOME=/tmp sh -c '{p.boot_cmd}') > /tmp/boot.log 2>&1 &
pid=$!
ok=0; for i in $(seq 1 {BOOT_WAIT_S}); do [ -d /proc/$pid ] && ! grep -q '^State:[[:space:]]*Z' /proc/$pid/status 2>/dev/null || break; if {probe} 2>/dev/null; then ok=1; break; fi; sleep 1; done
if [ $ok -eq 0 ]; then echo SHARLEY_BOOT_FAILED; tail -n 40 /tmp/boot.log; exit 3; fi
cd /in/t && COLUMNS=1000 PYTHONDONTWRITEBYTECODE=1 BASE_URL=http://127.0.0.1:{p.port} {run_tests}
"""


def docker_argv(name: str, image: str, script: str) -> list[str]:
    """No bind mounts at all: nothing from the host filesystem is visible to the untrusted app."""
    return ["docker", "run", "--rm", "-i", "--name", name, "--network", "none", "--read-only",
            "--tmpfs", "/app:rw,exec,size=256m", "--tmpfs", "/tmp:rw,exec,size=128m,mode=1777",
            "--tmpfs", "/in:rw,exec,size=128m,mode=0700",
            "--cap-drop", "ALL", "--cap-add", "SETUID", "--cap-add", "SETGID", "--cap-add", "CHOWN",
            "--security-opt", "no-new-privileges", "--pids-limit", "256", "--memory", "512m", "--cpus", "1",
            "-u", "0:0", image, "sh", "-c", script]


def pack(staging: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for child in sorted(staging.iterdir()):
            tar.add(child, arcname=child.name)  # symlinks stay symlinks
    return buf.getvalue()


class DockerSandbox(Sandbox):
    name = "docker"

    def __init__(self, executor: Executor = subprocess_exec, images: dict[str, str] | None = None):
        self.exec, self.images = executor, images or IMAGES

    def health(self) -> bool:
        return self.exec(["docker", "info"], 10, None).returncode == 0

    def run(self, workspace, tests, stack, *, timeout_s=180) -> RunReport:
        name = f"sharley-{uuid.uuid4().hex[:12]}"
        with tempfile.TemporaryDirectory(prefix="sharley-run-") as tmp:
            staging = Path(tmp)
            shutil.copytree(workspace, staging / "work", ignore=IGNORE, symlinks=True)
            for t in tests:  # pristine tests from the bank, never the workspace copies
                dest = staging / "t" / t.file
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(t.code)
            script = run_script(stack, [t.file for t in tests])
            try:
                res = self.exec(docker_argv(name, self.images[stack], script), timeout_s, pack(staging))
            finally:
                self.exec(["docker", "rm", "-f", name], 15, None)
        if res.timed_out:
            return RunReport(timed_out=True, results=[])
        if "SHARLEY_BOOT_FAILED" in res.stdout or res.returncode in (125, 126, 127):
            return RunReport(boot_ok=False, build_output=(res.stdout + res.stderr)[-1500:])
        parse = parse_pytest if stack == "docker-api" else parse_vitest
        return RunReport(results=parse(res.stdout, tests))
