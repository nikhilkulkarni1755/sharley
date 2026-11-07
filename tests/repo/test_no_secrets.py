import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "URI")


def tracked():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return out.split()


def test_only_env_example_is_tracked():
    envs = [f for f in tracked() if Path(f).name.startswith(".env")]
    assert envs == [".env.example"]


def test_env_example_has_no_secret_values():
    for line in (ROOT / ".env.example").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            name, value = line.split("=", 1)
            if any(m in name for m in SECRET_MARKERS):
                assert value == "", f"{name} must be blank in .env.example"


def test_gitignore_blocks_env_files():
    for name in (".env", ".env.local", ".env.production"):
        r = subprocess.run(["git", "check-ignore", "-q", name], cwd=ROOT)
        assert r.returncode == 0, f"{name} is not git-ignored"
