"""Local Docker sandbox: no network, read-only root, dropped capabilities, resource limits."""
import shutil
import subprocess
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


Executor = Callable[[list[str], float], ExecResult]


def subprocess_exec(argv: list[str], timeout: float) -> ExecResult:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, errors="replace")
        return ExecResult(p.returncode, p.stdout, p.stderr)
    except subprocess.TimeoutExpired as e:
        return ExecResult(124, (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""),
                          "", timed_out=True)
    except FileNotFoundError:
        return ExecResult(127, "", "docker not installed")


def run_script(stack: StackName, files: list[str]) -> str:
    p = PROFILES[stack]
    url = f"http://127.0.0.1:{p.port}{p.health_path}"
    probe = (f"python -c \"import urllib.request as u;u.urlopen('{url}',timeout=1)\"" if stack == "docker-api"
             else f"node -e \"fetch('{url}').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))\"")
    run_tests = ("python -m pytest -q -rA --tb=short -p no:cacheprovider " + " ".join(files) if stack == "docker-api"
                 else "npx vitest run --reporter=json " + " ".join(files))
    return f"""cp -r /work/. /app/ && cp -r /tests/. /app/ && cd /app
({p.boot_cmd}) > /tmp/boot.log 2>&1 &
pid=$!
ok=0; for i in $(seq 1 {BOOT_WAIT_S}); do kill -0 $pid 2>/dev/null || break; if {probe} 2>/dev/null; then ok=1; break; fi; sleep 1; done
if [ $ok -eq 0 ]; then echo SHARLEY_BOOT_FAILED; tail -n 40 /tmp/boot.log; exit 3; fi
BASE_URL=http://127.0.0.1:{p.port} {run_tests}
"""


def docker_argv(name: str, image: str, staging: Path) -> list[str]:
    return ["docker", "run", "--rm", "--name", name, "--network", "none", "--read-only",
            "--tmpfs", "/app:rw,exec,size=256m,uid=65534,gid=65534", "--tmpfs", "/tmp:rw,exec,size=128m,uid=65534,gid=65534",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "256",
            "--memory", "512m", "--cpus", "1", "-u", "65534:65534",
            "-v", f"{staging}/work:/work:ro", "-v", f"{staging}/tests:/tests:ro", "-v", f"{staging}/harness:/harness:ro",
            image, "sh", "/harness/run.sh"]


class DockerSandbox(Sandbox):
    name = "docker"

    def __init__(self, executor: Executor = subprocess_exec, images: dict[str, str] | None = None):
        self.exec, self.images = executor, images or IMAGES

    def health(self) -> bool:
        return self.exec(["docker", "info"], 10).returncode == 0

    def run(self, workspace, tests, stack, *, timeout_s=180) -> RunReport:
        name = f"sharley-{uuid.uuid4().hex[:12]}"
        with tempfile.TemporaryDirectory(prefix="sharley-run-") as tmp:
            staging = Path(tmp)
            shutil.copytree(workspace, staging / "work", ignore=IGNORE, symlinks=True)
            for t in tests:  # pristine tests from the bank, never the workspace copies
                dest = staging / "tests" / t.file
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(t.code)
            (staging / "harness").mkdir()
            (staging / "harness" / "run.sh").write_text(run_script(stack, [t.file for t in tests]))
            for d in staging.iterdir():  # container runs as nobody
                d.chmod(0o755)
            try:
                res = self.exec(docker_argv(name, self.images[stack], staging), timeout_s)
            finally:
                self.exec(["docker", "rm", "-f", name], 15)
        if res.timed_out:
            return RunReport(timed_out=True, results=[])
        if "SHARLEY_BOOT_FAILED" in res.stdout or res.returncode in (125, 126, 127):
            return RunReport(boot_ok=False, build_output=(res.stdout + res.stderr)[-1500:])
        parse = parse_pytest if stack == "docker-api" else parse_vitest
        return RunReport(results=parse(res.stdout, tests))
