"""`sharley` command line: spec, bank, check."""
import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TextIO

from sharley.gate import service
from sharley.gate.context import Context
from sharley.gate.git import GhHost
from sharley.gate.watch import watch_once
from sharley.gate.report import exit_code, github_annotation, render
from sharley.intake import IntakeInput, build_spec
from sharley.intake.files import load_codebase
from sharley.judge import IndependenceError, load_bank
from sharley.runner.docker import IMAGES
from sharley.schemas import ModelRef, Spec, TestBank

OK, FAILED, USAGE, INCOMPLETE = 0, 1, 2, 3


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sharley", description="Independent verifier for AI-written code")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("spec", help="turn text, an image or a repo into spec.json")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--text", type=Path)
    g.add_argument("--image", type=Path)
    g.add_argument("--repo", type=Path)
    s.add_argument("--out", type=Path, default=Path("spec.json"))
    b = sub.add_parser("bank", help="generate tests, split example/sealed, publish examples")
    b.add_argument("--spec", type=Path, required=True)
    b.add_argument("--workspace", type=Path, required=True, help="where example tests are written for the implementer")
    b.add_argument("--repo", type=Path, help="existing codebase (for env checks)")
    b.add_argument("--stack", choices=["nextjs", "docker-api"])
    b.add_argument("--seed", type=int, default=0)
    b.add_argument("--bank-out", type=Path, help="also write the sealed bank JSON here (keep it secret)")
    b.add_argument("--allow-partial", action="store_true")
    c = sub.add_parser("check", help="judge a workspace against the sealed tests")
    src = c.add_mutually_exclusive_group(required=True)
    src.add_argument("--bank", help="bank key in the repository")
    src.add_argument("--bank-file", type=Path)
    c.add_argument("--workspace", type=Path, default=Path("."))
    c.add_argument("--stack", choices=["nextjs", "docker-api"], default="docker-api")
    c.add_argument("--implementer-model", required=True)
    c.add_argument("--implementer-family", required=True)
    c.add_argument("--json", action="store_true")
    w = sub.add_parser("watch", help="judge merged changes; open a revert PR when sealed tests fail")
    w.add_argument("--bank-file", type=Path, required=True)
    w.add_argument("--repo-path", type=Path, default=Path("."))
    w.add_argument("--stack", choices=["nextjs", "docker-api"], default="docker-api")
    w.add_argument("--implementer-model", required=True)
    w.add_argument("--implementer-family", required=True)
    w.add_argument("--interval", type=int, default=0, help="seconds between polls; 0 = run once")
    sub.add_parser("images", help="build the sandbox runner images")
    sv = sub.add_parser("serve", help="run the HTTP API for the web board")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    return p


def cmd_spec(a, ctx: Context, out: TextIO) -> int:
    if a.text:
        inp = IntakeInput(text=a.text.read_text())
    elif a.image:
        inp = IntakeInput(image=a.image.read_bytes())
    else:
        inp = IntakeInput(files=load_codebase(a.repo))
    spec = build_spec(ctx.verifier, inp, long_chain=ctx.long_context if ctx.long_context.healthy.get("subq") else None,
                      repo=ctx.repo)
    a.out.write_text(spec.model_dump_json(indent=2))
    observed = sum(r.evidence.kind == "observed" for r in spec.requirements)
    print(f"{len(spec.requirements)} requirements ({observed} observed, {len(spec.requirements) - observed} inferred), "
          f"coverage {spec.coverage_pct}%, spec {spec.spec_hash[:12]} -> {a.out}", file=out)
    return OK


def cmd_bank(a, ctx: Context, out: TextIO) -> int:
    spec = Spec.model_validate_json(a.spec.read_text())
    files = load_codebase(a.repo) if a.repo else None
    try:
        bank = service.make_bank(spec, ctx.repo, ctx.verifier, stack=a.stack, files=files, seed=a.seed,
                                 allow_partial=a.allow_partial)
    except service.IncompleteBank as e:
        print(f"error: {e}", file=out)
        return INCOMPLETE
    service.publish_examples(bank, spec, a.workspace, a.stack)
    if a.bank_out:
        a.bank_out.write_text(bank.model_dump_json())
    print(f"bank {bank.spec_hash}:{bank.seed}: {len(bank.examples)} example tests -> {a.workspace}, "
          f"{len(bank.sealed)} sealed (hidden)", file=out)
    return OK


def cmd_check(a, ctx: Context, out: TextIO) -> int:
    bank = TestBank.model_validate_json(a.bank_file.read_text()) if a.bank_file else load_bank(ctx.repo, a.bank)
    impl = ModelRef(provider="external", model=a.implementer_model, family=a.implementer_family)
    try:
        v = service.check_submission(bank, a.workspace, ctx.sandbox, a.stack, impl, repo=ctx.repo)
    except IndependenceError as e:
        print(f"error: {e}", file=out)
        return USAGE
    print(v.model_dump_json(indent=2) if a.json else render(v), file=out)
    if note := github_annotation(v):
        print(note, file=out)
    return exit_code(v)


def cmd_watch(a, ctx: Context, out: TextIO, host=None, sleep=time.sleep) -> int:
    bank = TestBank.model_validate_json(a.bank_file.read_text())
    host = host or GhHost(a.repo_path)
    impl = ModelRef(provider="external", model=a.implementer_model, family=a.implementer_family)
    while True:
        for r in watch_once(host=host, bank=bank, sandbox=ctx.sandbox, stack=a.stack, implementer=impl, repo=ctx.repo):
            print(f"PR #{r.change.pr} ({r.change.sha[:8]}): {r.status}" + (f" -> revert {r.revert_url}" if r.revert_url else ""), file=out)
        if not a.interval:
            return OK
        sleep(a.interval)


def cmd_images(a, ctx: Context, out: TextIO) -> int:
    img = Path(__file__).resolve().parents[1] / "runner" / "images"
    for stack, dockerfile in (("docker-api", "python.Dockerfile"), ("nextjs", "node.Dockerfile")):
        r = subprocess.run(["docker", "build", "-q", "-f", str(img / dockerfile), "-t", IMAGES[stack], str(img)])
        print(f"{IMAGES[stack]}: {'built' if r.returncode == 0 else 'FAILED'}", file=out)
        if r.returncode:
            return FAILED
    return OK


def cmd_serve(a, ctx: Context, out: TextIO) -> int:
    import uvicorn

    from sharley.api import create_app

    uvicorn.run(create_app(ctx, [o for o in ctx.env.get("SHARLEY_CORS_ORIGINS", "http://localhost:3000").split(",") if o]),
                host=a.host, port=a.port)
    return OK


COMMANDS: dict[str, Callable] = {"spec": cmd_spec, "bank": cmd_bank, "check": cmd_check, "watch": cmd_watch,
                                 "images": cmd_images, "serve": cmd_serve}


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None, out: TextIO | None = None,
         context_factory: Callable[[Mapping[str, str]], Context] = Context.from_env) -> int:
    out = out or sys.stdout
    env = os.environ if env is None else env
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    try:
        return COMMANDS[args.cmd](args, context_factory(env), out)
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"error: {e}", file=out)
        return USAGE
