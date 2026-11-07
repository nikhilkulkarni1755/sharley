"""Message schemas shared by the uAgents, the CLI and the web fallback (identical on every path)."""
try:
    from uagents import Model
except ImportError:  # offline/CI without uagents: same schemas, plain pydantic
    from pydantic import BaseModel as Model


class BankRequest(Model):
    spec_json: str


class BankReply(Model):
    ok: bool
    bank_key: str = ""
    examples: int = 0
    sealed: int = 0
    error: str = ""


class JudgeRequest(Model):
    bank_key: str
    repo_url: str
    branch: str = ""
    implementer_model: str = "unknown"
    implementer_family: str = "external"


class JudgeReply(Model):
    ok: bool
    verdict_json: str = ""
    error: str = ""
