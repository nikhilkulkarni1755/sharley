import json

import httpx
import pytest

from sharley.harness import ProviderError
from sharley.providers import implementer_chain, is_offline, long_context_chain, verifier_chain
from sharley.providers.anthropic import AnthropicProvider
from sharley.providers.gemini import GeminiProvider
from sharley.providers.openai_compat import OpenAICompatProvider


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def oai(handler, **kw):
    return OpenAICompatProvider("meta", "meta", api_key="sk-secret", base_url="http://x/v1", model="m",
                                client=client(handler), **kw)


# ---- intended use
def test_openai_compat_request_and_parse():
    seen = {}

    def h(req):
        seen["auth"], seen["body"] = req.headers["authorization"], json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    assert oai(h).complete("sys", "usr") == "hi"
    assert seen["auth"] == "Bearer sk-secret"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}


def test_openai_compat_sends_images_as_data_uris():
    seen = {}

    def h(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    oai(h).complete("s", "u", images=[b"\x89PNG"])
    assert seen["body"]["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_anthropic_request_and_parse():
    def h(req):
        assert req.headers["x-api-key"] == "k" and req.url.path == "/v1/messages"
        return httpx.Response(200, json={"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]})

    p = AnthropicProvider(api_key="k", model="claude-sonnet-5-5", client=client(h))
    assert p.complete("s", "u") == "ab"


def test_gemini_omits_forbidden_params_and_sets_thinking_level():
    seen = {}

    def h(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"outputs": [{"type": "text", "text": "done"}]})

    p = GeminiProvider(api_key="g", model="gemini-4-argon", thinking_level="high", client=client(h))
    assert p.complete("s", "u") == "done"
    flat = json.dumps(seen["body"])
    for banned in ("temperature", "top_p", "top_k", "cached_content", "thinking_budget"):
        assert banned not in flat
    assert seen["body"]["generation_config"] == {"thinking_level": "high"}
    assert p.timeout >= 900  # long runs need long timeouts


def test_health_requires_configuration():
    assert oai(lambda r: httpx.Response(200)).health() is True
    unset = OpenAICompatProvider("meta", "meta", client=client(lambda r: httpx.Response(200)))
    assert unset.health() is False


def test_local_health_probes_endpoint():
    ok = OpenAICompatProvider("local", "local", requires_key=False, base_url="http://l/v1", model="m",
                              client=client(lambda r: httpx.Response(200, json={})))
    down = OpenAICompatProvider("local", "local", requires_key=False, base_url="http://l/v1", model="m",
                                client=client(lambda r: (_ for _ in ()).throw(httpx.ConnectError("no"))))
    assert ok.health() is True and down.health() is False


# ---- chains and offline
def test_verifier_and_implementer_chains_are_independent_families():
    v = [p.family for p in verifier_chain({}).providers]
    i = [p.family for p in implementer_chain({}).providers]
    assert v[0] == "meta" and i[0] == "google"


@pytest.mark.parametrize("val", ["1", "true", "YES"])
def test_offline_flag_keeps_only_local(val):
    env = {"SHARLEY_OFFLINE": val}
    assert is_offline(env)
    for chain in (verifier_chain(env), implementer_chain(env), long_context_chain(env)):
        assert [p.name for p in chain.providers] == ["local"]


def test_offline_flag_off_by_default():
    assert not is_offline({}) and not is_offline({"SHARLEY_OFFLINE": "0"})


# ---- misuse / failure handling
@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_errors_become_provider_errors(status):
    with pytest.raises(ProviderError, match=str(status)):
        oai(lambda r: httpx.Response(status, text="boom")).complete("s", "u")


def test_api_key_never_leaks_in_errors():
    echo = lambda r: httpx.Response(401, text="bad key sk-secret")  # noqa: E731
    with pytest.raises(ProviderError) as e:
        oai(echo).complete("s", "u")
    assert "sk-secret" not in str(e.value)

    def boom(req):
        raise httpx.ConnectError("cannot reach sk-secret host")

    with pytest.raises(ProviderError) as e2:
        oai(boom).complete("s", "u")
    assert "sk-secret" not in str(e2.value)


@pytest.mark.parametrize("body", [{}, {"choices": []}, {"choices": [{"message": {}}]}])
def test_malformed_success_bodies_rejected(body):
    with pytest.raises(ProviderError):
        oai(lambda r: httpx.Response(200, json=body)).complete("s", "u")


def test_non_json_body_rejected():
    with pytest.raises(ProviderError, match="non-JSON"):
        oai(lambda r: httpx.Response(200, text="<html>")).complete("s", "u")


def test_gemini_rejects_unknown_thinking_level():
    with pytest.raises(ValueError):
        GeminiProvider(api_key="g", model="m", thinking_level="extreme")
    with pytest.raises(ValueError):
        GeminiProvider(api_key="g", model="m", thinking_level="budget:1000")


# ---- image media types
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 10
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 10


@pytest.mark.parametrize("data,mime", [(JPEG, "image/jpeg"), (PNG_BYTES, "image/png"), (b"RIFF\x00\x00\x00\x00WEBPxx", "image/webp"),
                                       (b"GIF89a...", "image/gif"), (b"unknown", "image/png")])
def test_sniff_mime_uses_magic_bytes(data, mime):
    from sharley.providers.base import sniff_mime
    assert sniff_mime(data) == mime


def test_jpeg_is_sent_with_a_jpeg_media_type_on_every_provider():
    seen = {}

    def anth(req):
        seen["anthropic"] = json.loads(req.content)["messages"][0]["content"][0]["source"]["media_type"]
        return httpx.Response(200, json={"content": [{"type": "text", "text": "x"}]})

    def oai(req):
        seen["openai"] = json.loads(req.content)["messages"][1]["content"][1]["image_url"]["url"][:15]
        return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})

    def gem(req):
        seen["gemini"] = json.loads(req.content)["input"][1]["mime_type"]
        return httpx.Response(200, json={"outputs": [{"type": "text", "text": "x"}]})

    AnthropicProvider(api_key="k", model="m", client=client(anth)).complete("s", "u", images=[JPEG])
    oai_p = OpenAICompatProvider("meta", "meta", api_key="k", base_url="http://x/v1", model="m", client=client(oai))
    oai_p.complete("s", "u", images=[JPEG])
    GeminiProvider(api_key="k", model="m", client=client(gem)).complete("s", "u", images=[JPEG])
    assert seen == {"anthropic": "image/jpeg", "openai": "data:image/jpeg", "gemini": "image/jpeg"}
