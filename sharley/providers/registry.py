"""Build fallback chains from environment. SHARLEY_OFFLINE=1 keeps only local providers."""
from collections.abc import Mapping

from sharley.harness.budget import Meter
from sharley.harness.chain import FallbackChain
from sharley.harness.provider import ModelProvider
from sharley.providers.anthropic import AnthropicProvider
from sharley.providers.gemini import GeminiProvider
from sharley.providers.openai_compat import OpenAICompatProvider


def is_offline(env: Mapping[str, str]) -> bool:
    return env.get("SHARLEY_OFFLINE", "0").strip().lower() in ("1", "true", "yes")


def _meter(env: Mapping[str, str]) -> Meter:
    return Meter.from_env(env)


def local(env: Mapping[str, str]) -> OpenAICompatProvider:
    return OpenAICompatProvider("local", "local", cost_rank=1, requires_key=False,
                                base_url=env.get("LOCAL_LLM_URL", ""), model=env.get("LOCAL_LLM_MODEL", ""))


def meta(env: Mapping[str, str]) -> OpenAICompatProvider:
    return OpenAICompatProvider("meta", "meta", cost_rank=7, api_key=env.get("META_API_KEY", ""),
                                base_url=env.get("META_BASE_URL", ""), model=env.get("META_MODEL", ""), meter=_meter(env))


def subq(env: Mapping[str, str]) -> OpenAICompatProvider:
    return OpenAICompatProvider("subq", "subquadratic", cost_rank=3, api_key=env.get("SUBQ_API_KEY", ""),
                                base_url=env.get("SUBQ_BASE_URL", ""), model=env.get("SUBQ_MODEL", ""), meter=_meter(env))


def anthropic(env: Mapping[str, str]) -> AnthropicProvider:
    return AnthropicProvider(api_key=env.get("ANTHROPIC_API_KEY", ""), model=env.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
                             meter=_meter(env))


def gemini(env: Mapping[str, str], model: str = "gemini-4-argon", thinking_level: str = "medium") -> GeminiProvider:
    return GeminiProvider(api_key=env.get("GEMINI_API_KEY", ""), model=model, thinking_level=thinking_level, meter=_meter(env))


def _chain(env: Mapping[str, str], ordered: list[ModelProvider]) -> FallbackChain:
    if is_offline(env):
        ordered = [p for p in ordered if p.name == "local"]
    return FallbackChain(ordered)


def verifier_chain(env: Mapping[str, str]) -> FallbackChain:
    """Meta first (independence story), then Claude, then the local model."""
    return _chain(env, [meta(env), anthropic(env), local(env)])


def implementer_chain(env: Mapping[str, str]) -> FallbackChain:
    return _chain(env, [gemini(env), anthropic(env), local(env)])


def long_context_chain(env: Mapping[str, str]) -> FallbackChain:
    """SubQ Snap for whole repos; callers fall back to chunked extraction on the verifier chain."""
    return _chain(env, [subq(env), local(env)])
