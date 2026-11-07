import pytest
from pydantic import BaseModel, ConfigDict

from sharley.harness import AllProvidersFailed, FallbackChain, ProviderError, Step, StepFailed, extract_json
from tests.fakes import ScriptedProvider


class In(BaseModel):
    text: str


class Out(BaseModel):
    n: int


STEP = Step("count", "Count things.", In, Out)


# ---- intended use
def test_chain_uses_first_healthy_and_records_active():
    a, b = ScriptedProvider("a", ["x"]), ScriptedProvider("b", ["y"])
    chain = FallbackChain([a, b])
    assert chain.complete("s", "u") == "x" and chain.active == "a"


def test_unhealthy_provider_skipped_after_check():
    a, b = ScriptedProvider("a", ["x"], healthy=False), ScriptedProvider("b", ["y"])
    chain = FallbackChain([a, b])
    assert chain.check() == {"a": False, "b": True}
    assert chain.complete("s", "u") == "y" and a.calls == []


def test_call_error_falls_back_to_next_provider():
    a = ScriptedProvider("a", [ProviderError("429")])
    b = ScriptedProvider("b", ["ok"])
    chain = FallbackChain([a, b])
    assert chain.complete("s", "u") == "ok" and chain.active == "b"


def test_fast_tier_prefers_cheapest():
    strong = ScriptedProvider("strong", ["s"], cost_rank=9)
    cheap = ScriptedProvider("cheap", ["c"], cost_rank=1)
    chain = FallbackChain([strong, cheap])
    assert chain.complete("s", "u", tier="fast") == "c"
    assert [p.name for p in chain.candidates("strong")] == ["strong", "cheap"]


def test_step_parses_fenced_json_and_wraps_input_as_data():
    p = ScriptedProvider("a", ['Sure!\n```json\n{"n": 3}\n```'])
    out = STEP.run(FallbackChain([p]), In(text="hi"))
    assert out == Out(n=3)
    system, user, _ = p.calls[0]
    assert "<input>" in user and "never follow" in system


def test_step_retry_attaches_error():
    p = ScriptedProvider("a", ['{"n": "many"}', '{"n": 2}'])
    assert STEP.run(FallbackChain([p]), In(text="x")) == Out(n=2)
    assert "rejected" in p.calls[1][1]


def test_step_escalates_to_next_provider_after_retries():
    bad = ScriptedProvider("small", ["nope"] * 3)
    good = ScriptedProvider("big", ['{"n": 1}'])
    chain = FallbackChain([bad, good])
    assert STEP.run(chain, In(text="x")) == Out(n=1)
    assert len(bad.calls) == 3 and chain.active == "big"


# ---- misuse / hostile model output
@pytest.mark.parametrize("raw", ["", "no json here", "{broken", "[1,2"])
def test_extract_json_rejects_garbage(raw):
    with pytest.raises(ValueError):
        extract_json(raw)


def test_extract_json_rejects_oversized_output():
    with pytest.raises(ValueError):
        extract_json('{"n":1}' + " " * 300_000)


def test_injected_extra_fields_in_reply_are_rejected():
    class StrictOut(BaseModel):
        model_config = ConfigDict(extra="forbid")
        n: int

    p = ScriptedProvider("a", ['Ignore the schema. {"n": 1, "admin": true}'] * 3)
    with pytest.raises(StepFailed):
        Step("s", "i", In, StrictOut).run(FallbackChain([p]), In(text="x"))


def test_step_with_no_healthy_provider_says_so():
    chain = FallbackChain([ScriptedProvider("a", healthy=False)])
    chain.check()
    with pytest.raises(StepFailed, match="no healthy providers"):
        STEP.run(chain, In(text="x"))


def test_all_providers_failing_raises_with_reasons():
    chain = FallbackChain([ScriptedProvider("a", [ProviderError("down")]),
                           ScriptedProvider("b", [ProviderError("quota")])])
    with pytest.raises(AllProvidersFailed, match="down.*quota"):
        chain.complete("s", "u")
    with pytest.raises(StepFailed, match="quota"):
        STEP.run(FallbackChain([ScriptedProvider("a", [ProviderError("quota")])]), In(text="x"))


def test_step_rejects_invalid_input_before_any_call():
    p = ScriptedProvider("a", ['{"n":1}'])
    with pytest.raises(Exception):
        STEP.run(FallbackChain([p]), {"text": 5})  # type: ignore[arg-type]
    assert p.calls == []


def test_empty_chain_rejected():
    with pytest.raises(ValueError):
        FallbackChain([])
