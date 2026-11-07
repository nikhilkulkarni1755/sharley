"""Repo jobs: clone a public GitHub repo onto the server, then either judge it against a pre-built sealed bank (the known
sample repos) or audit it with freshly generated tests. Progress is streamed as run events."""
import shutil
from collections.abc import Callable
from pathlib import Path

from agents.repo import BadRepo
from sharley.api.guard import Guard
from sharley.api.runs import RecordingSandbox, Run, result_events
from sharley.gate import service
from sharley.gate.context import Context
from sharley.intake import IntakeInput, build_spec
from sharley.intake.codebase import summarize_codebase
from sharley.intake.files import load_codebase
from sharley.judge import export_workspace
from sharley.schemas import ModelRef, TestBank

Fetch = Callable[[str, str], Path]
FINDING_CLIP = 400


def stage(run: Run, name: str, detail: str = "") -> None:
    run.emit({"type": "stage", "stage": name, "detail": detail})


def run_repo_job(ctx: Context, run: Run, url: str, branch: str, bank: TestBank | None, fetch: Fetch, guard: Guard) -> None:
    src: Path | None = None
    try:
        stage(run, "cloning", url)
        src = fetch(url, branch)
        files = load_codebase(src)
        summary = summarize_codebase(files)
        run.emit({"type": "surface", "stack": summary.stack, "files": len(files), "routes": len(summary.routes),
                  "env_vars": len(summary.env_vars)})
        if bank is not None:
            _judge_sealed(ctx, run, src, bank)
        else:
            _audit(ctx, run, src, files, summary.stack or "docker-api")
    except BadRepo as e:
        run.emit({"type": "error", "detail": str(e)})
    except Exception as e:  # never surface a stack trace; the board shows this as a retryable message
        run.emit({"type": "error", "detail": f"{type(e).__name__}: {e}"[:300]})
    finally:
        guard.release_run()
        if src is not None:
            shutil.rmtree(src.parent, ignore_errors=True)
        run.finish()


def _judge_sealed(ctx: Context, run: Run, src: Path, bank: TestBank) -> None:
    stage(run, "running_tests", "hidden tests prepared ahead of time; judging in the sandbox")
    export_workspace(bank, src)  # the visible example tests the implementer would have
    sandbox = RecordingSandbox(ctx.sandbox)
    verdict = service.check_submission(bank, src, sandbox, "docker-api", ModelRef(provider="github", model="repo", family="human"),
                                       repo=ctx.repo)
    for ev in result_events(bank, sandbox.last, verdict, []):
        run.emit(ev)


def _audit(ctx: Context, run: Run, src: Path, files: dict[str, str], stack: str) -> None:
    stage(run, "analyzing", f"{len(files)} files")
    spec = build_spec(ctx.verifier, IntakeInput(files=files), repo=ctx.repo)
    stage(run, "writing_tests", f"{len(spec.requirements)} requirements")
    bank = service.make_bank(spec, ctx.repo, ctx.verifier, stack=stack, files=files, allow_partial=True)
    stage(run, "running_tests", f"{len(bank.tests)} generated tests")
    report = ctx.sandbox.run(src, bank.tests, stack, timeout_s=180)
    by_id = {t.id: t for t in bank.tests}
    results = {r.test_id: r for r in report.results}
    failed = [r for r in report.results if not r.passed]
    texts = {q.id: q.text for q in spec.requirements}
    for r in failed:
        t = by_id[r.test_id]
        run.emit({"type": "finding", "id": t.id, "name": t.name, "family": t.family, "requirement_ids": t.requirement_ids,
                  "requirement_text": " ".join(texts[i] for i in t.requirement_ids if i in texts),
                  "kind": r.kind, "message": (r.output or t.hint)[:FINDING_CLIP]})
    total = len(results) if report.boot_ok else len(bank.tests)
    run.emit({"type": "report", "total": total, "passed": total - len(failed) if report.boot_ok else 0, "failed": len(failed),
              "boot_ok": report.boot_ok, "build_output": report.build_output[-FINDING_CLIP:]})
