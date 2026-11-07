import json
import threading

import httpx
import pytest

from sharley.gate.cli import main
from sharley.harness import ProviderError
from sharley.harness.budget import BudgetExceeded, Meter
from sharley.providers.anthropic import AnthropicProvider
from sharley.providers.openai_compat import OpenAICompatProvider


def meter(tmp_path, limit=1.0, **kw):
    return Meter(tmp_path / "ledger.json", limit, **kw)


# ---- pricing math
def test_cost_uses_published_prices_and_cache_multipliers(tmp_path):
    m = meter(tmp_path)
    assert m.cost("claude-sonnet-5-5", 1_000_000, 1_000_000) == pytest.approx(12.0)
    assert m.cost("claude-sonnet-5-5", 0, 0, cache_read=1_000_000) == pytest.approx(0.2)
    assert m.cost("claude-sonnet-5-5", 0, 0, cache_write=1_000_000) == pytest.approx(2.5)
    assert m.cost("claude-haiku-5-5", 1_000_000, 0) == pytest.approx(0.10)


def test_unknown_models_are_priced_conservatively_not_free(tmp_path):
    m = meter(tmp_path)
    assert m.cost("mystery-model", 1_000_000, 0) >= m.cost("claude-opus-5-5", 1_000_000, 0)
    assert meter(tmp_path, prices={"muse": (1.0, 2.0)}).cost("muse", 1_000_000, 1_000_000) == pytest.approx(3.0)


# ---- cap
def test_cap_blocks_further_paid_calls_but_never_local_ones(tmp_path):
    m = meter(tmp_path, limit=0.01)
    m.check("anthropic")
    m.charge("anthropic", "claude-sonnet-5-5", 1_000_000, 0)
    with pytest.raises(BudgetExceeded, match="spend cap"):
        m.check("anthropic")
    m.check("local")  # free


def test_local_provider_is_free_and_still_counted(tmp_path):
    m = meter(tmp_path)
    assert m.charge("local", "whatever", 10**9, 10**9) == 0.0
    assert m.spent() == 0.0


def test_ledger_persists_across_instances(tmp_path):
    meter(tmp_path).charge("anthropic", "claude-sonnet-5-5", 500_000, 0)
    m2 = meter(tmp_path)
    assert m2.spent() == pytest.approx(1.0)
    m2.charge("meta", "muse", 0, 100_000)
    assert json.loads((tmp_path / "ledger.json").read_text())["by_provider"].keys() == {"anthropic", "meta"}


def test_corrupt_ledger_does_not_crash_or_unlock_silently(tmp_path):
    (tmp_path / "ledger.json").write_text("{not json")
    m = meter(tmp_path)
    assert m.spent() == 0.0
    m.charge("anthropic", "claude-sonnet-5-5", 1000, 1000)
    assert m.spent() > 0


def test_concurrent_charges_are_not_lost(tmp_path):
    m = meter(tmp_path, limit=100)
    ts = [threading.Thread(target=lambda: [m.charge("anthropic", "claude-haiku-5-5", 1_000_000, 0) for _ in range(10)]) for _ in range(5)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert m.spent() == pytest.approx(5.0)


def test_from_env_reads_cap_home_and_meta_price_override(tmp_path):
    m = Meter.from_env({"SHARLEY_HOME": str(tmp_path), "SHARLEY_BUDGET_USD": "7.5", "META_MODEL": "muse-spark-1.3",
                        "META_PRICE_IN": "1", "META_PRICE_OUT": "4"})
    assert m.limit == 7.5 and m.cost("muse-spark-1.3", 1_000_000, 1_000_000) == pytest.approx(5.0)
    assert Meter.from_env({"SHARLEY_HOME": str(tmp_path)}).limit == 15.0


# ---- providers charge from real usage blocks
def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_anthropic_calls_are_metered_and_cut_off_at_the_cap(tmp_path):
    m = meter(tmp_path, limit=0.5)
    calls = []

    def h(req):
        calls.append(1)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "x"}],
                                         "usage": {"input_tokens": 100_000, "output_tokens": 30_000}})  # $0.50

    p = AnthropicProvider(api_key="k", model="claude-sonnet-5-5", client=client(h), meter=m)
    assert p.complete("s", "u") == "x"
    assert m.spent() == pytest.approx(0.5)
    with pytest.raises(BudgetExceeded):
        p.complete("s", "u")
    assert len(calls) == 1  # the second request never left the machine


def test_budget_exceeded_is_a_provider_error_so_chains_fall_back(tmp_path):
    assert issubclass(BudgetExceeded, ProviderError)


def test_openai_compat_metering_and_null_reasoning_content(tmp_path):
    m = meter(tmp_path, limit=100, prices={"muse": (1.0, 4.0)})
    ok = OpenAICompatProvider("meta", "meta", api_key="k", base_url="http://x/v1", model="muse", meter=m, client=client(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}],
                                            "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 250_000}})))
    assert ok.complete("s", "u") == "hi" and m.spent() == pytest.approx(2.0)
    reasoning = OpenAICompatProvider("meta", "meta", api_key="k", base_url="http://x/v1", model="muse", meter=m, client=client(
        lambda r: httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": None}}],
                                            "usage": {"prompt_tokens": 15, "completion_tokens": 20}})))
    with pytest.raises(ProviderError, match="empty content.*length"):
        reasoning.complete("s", "u")
    assert m.spent() > 2.0  # the wasted reasoning tokens are still billed in the ledger


def test_spend_command_prints_the_ledger(tmp_path):
    from io import StringIO
    Meter(tmp_path / "ledger.json", 15).charge("anthropic", "claude-sonnet-5-5", 1_000_000, 0)
    out = StringIO()
    assert main(["spend"], env={"SHARLEY_HOME": str(tmp_path), "SHARLEY_BUDGET_USD": "15", "SHARLEY_OFFLINE": "1"}, out=out) == 0
    assert "spent $2.0000 of $15.00" in out.getvalue() and "anthropic" in out.getvalue()
