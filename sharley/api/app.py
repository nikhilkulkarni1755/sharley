"""HTTP API: the board's window into the verifier. Sealed test content never leaves this process."""
import asyncio
import base64
import json
import shutil
import tempfile
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents.conversation import Conversation
from agents.services import LocalServices
from sharley.api.guard import Guard
from sharley.api.runs import RecordingSandbox, Run, RunRegistry, result_events
from sharley.api.views import bank_view
from sharley.gate import service
from sharley.gate.context import Context
from sharley.implementer.agent import safe_target
from sharley.intake import IntakeInput, build_spec
from sharley.judge import export_workspace, load_bank
from sharley.profiles import PROFILES
from sharley.schemas import ModelRef, Spec
from sharley.skills import SkillStore

MAX_TEXT = 200_000
MAX_FILES = 80
MAX_FILE_CHARS = 100_000
DEMO_FIXTURE = Path(__file__).resolve().parents[2] / "evals" / "fixtures" / "demo.json"


class SpecRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)


class ImageSpecRequest(BaseModel):
    image_b64: str = Field(min_length=1, max_length=11_000_000)  # PNG or JPEG, base64


class ChatRequest(BaseModel):
    session: str = Field(min_length=1, max_length=64, pattern=r"^[\w.-]+$")
    text: str = Field(max_length=MAX_TEXT)


class BankRequest(BaseModel):
    spec_hash: str
    stack: str = "docker-api"
    seed: int = 0


class RunRequest(BaseModel):
    bank: str
    implementer_model: str = Field(min_length=1, max_length=100)
    implementer_family: str = Field(min_length=1, max_length=50)
    files: dict[str, str] = Field(max_length=MAX_FILES)
    stack: str = "docker-api"


def create_app(ctx: Context, cors_origins: list[str] | None = None, guard: Guard | None = None) -> FastAPI:
    app = FastAPI(title="Sharley", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=cors_origins or ["http://localhost:3000"],
                       allow_origin_regex=ctx.env.get("SHARLEY_CORS_ORIGIN_REGEX") or None,
                       allow_methods=["GET", "POST"], allow_headers=["content-type"])
    registry = RunRegistry()
    guard = guard or Guard.from_env(ctx.env)
    admin = Depends(guard.require_admin)
    chat = Conversation(LocalServices(ctx))

    @app.get("/api/health")
    def health():
        return {"status": "ok", "offline": ctx.env.get("SHARLEY_OFFLINE", "0") in ("1", "true"),
                "providers": ctx.verifier.healthy, "active_provider": ctx.verifier.active,
                "sandbox": ctx.sandbox.name}

    @app.post("/api/specs")
    def create_spec(req: SpecRequest, _: None = admin):
        try:
            spec = build_spec(ctx.verifier, IntakeInput(text=req.text), repo=ctx.repo)
        except Exception as e:  # provider chain exhausted etc: a clear retryable message, never a stack trace
            raise HTTPException(status_code=503, detail=f"intake failed, please retry: {type(e).__name__}") from None
        return {**spec.model_dump(), "active_provider": ctx.verifier.active}

    @app.post("/api/specs/image")
    def create_spec_from_image(req: ImageSpecRequest, _: None = admin):
        try:
            data = base64.b64decode(req.image_b64, validate=True)
            spec = build_spec(ctx.verifier, IntakeInput(image=data), repo=ctx.repo)
        except ValueError as e:  # bad base64, not PNG/JPEG, too large, unreadable
            raise HTTPException(status_code=422, detail=str(e)) from None
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"intake failed, please retry: {type(e).__name__}") from None
        return {**spec.model_dump(), "active_provider": ctx.verifier.active}

    @app.post("/api/banks")
    def create_bank(req: BankRequest, _: None = admin):
        doc = ctx.repo.get("specs", req.spec_hash)
        if doc is None:
            raise HTTPException(status_code=404, detail="unknown spec")
        if req.stack not in PROFILES:
            raise HTTPException(status_code=422, detail="unsupported stack")
        try:
            bank = service.make_bank(Spec.model_validate(doc), ctx.repo, ctx.verifier, stack=req.stack, seed=req.seed)
        except service.IncompleteBank as e:
            raise HTTPException(status_code=422, detail=str(e)) from None
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"test generation failed, please retry: {type(e).__name__}") from None
        return bank_view(bank)

    @app.get("/api/banks/{key}")
    def get_bank(key: str):
        try:
            return bank_view(load_bank(ctx.repo, key))
        except KeyError:
            raise HTTPException(status_code=404, detail="unknown bank") from None

    @app.post("/api/runs", status_code=202)
    def start_run(req: RunRequest, request: Request):
        try:
            bank = load_bank(ctx.repo, req.bank)
        except KeyError:
            raise HTTPException(status_code=404, detail="unknown bank") from None
        if req.stack not in PROFILES:
            raise HTTPException(status_code=422, detail="unsupported stack")
        if bank.author and bank.author.family == req.implementer_family:
            raise HTTPException(status_code=422, detail="implementer and verifier must be different model families")
        if any(len(c) > MAX_FILE_CHARS for c in req.files.values()):
            raise HTTPException(status_code=413, detail="file too large")
        guard.acquire_run(request)
        workspace = Path(tempfile.mkdtemp(prefix="sharley-sub-"))
        try:
            export_workspace(bank, workspace)
            test_dir = PROFILES[req.stack].test_dir
            rejected = []
            for rel, content in req.files.items():
                target = safe_target(workspace, rel, test_dir)
                if target is None:
                    rejected.append(rel)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            run = registry.create()
            threading.Thread(target=_execute, args=(ctx, bank, workspace, req, run, rejected, guard), daemon=True).start()
        except Exception:
            guard.release_run()
            shutil.rmtree(workspace, ignore_errors=True)
            raise
        return {"run_id": run.id, "rejected_paths": rejected}

    @app.get("/api/runs/{run_id}/events")
    async def run_events(run_id: str):
        run = registry.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="unknown run")

        async def stream():
            sent = 0
            for _ in range(2400):  # ~2 minutes at 50ms
                for ev in run.snapshot(sent):
                    sent += 1
                    yield f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n"
                if run.done and not run.snapshot(sent):
                    return
                await asyncio.sleep(0.05)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.post("/api/chat")
    def chat_endpoint(req: ChatRequest, _: None = admin):
        """Same conversation the ASI:One agents run, for when Agentverse is unreachable."""
        reply = chat.handle(req.session, req.text)
        return {"text": reply.text, "card": reply.card}

    @app.get("/api/samples")
    def samples():
        """Playground targets: spec + flawed source (no hints) + the sealed bank that will judge it. Sealed code never leaves."""
        from evals.sample_backends import NAMES, TITLES, load_index, playground_files, spec_text

        index = load_index(Path(ctx.env.get("SHARLEY_HOME", ".sharley")))
        out = []
        for name in NAMES:
            try:
                bank = bank_view(load_bank(ctx.repo, index[name])) if name in index else None
            except KeyError:
                bank = None
            out.append({"name": name, "title": TITLES[name], "spec": spec_text(name), "files": playground_files(name), "bank": bank})
        return out

    @app.get("/api/skills/timeline")
    def timeline():
        return [v.model_dump() for v in SkillStore(ctx.repo).timeline()]

    @app.get("/api/demo")
    def demo():
        if not DEMO_FIXTURE.exists():
            raise HTTPException(status_code=404, detail="demo fixture not built; run `python -m evals.fixtures.build`")
        return json.loads(DEMO_FIXTURE.read_text())

    return app


def _execute(ctx: Context, bank, workspace: Path, req: RunRequest, run: Run, rejected: list[str], guard: Guard) -> None:
    sandbox = RecordingSandbox(ctx.sandbox)
    try:
        verdict = service.check_submission(bank, workspace, sandbox, req.stack,
                                           ModelRef(provider="external", model=req.implementer_model,
                                                    family=req.implementer_family), repo=ctx.repo)
        for ev in result_events(bank, sandbox.last, verdict, rejected):
            run.emit(ev)
    except Exception as e:
        run.emit({"type": "error", "detail": f"{type(e).__name__}: {e}"[:300]})
    finally:
        guard.release_run()
        shutil.rmtree(workspace, ignore_errors=True)
        run.finish()
