import base64

from sharley.harness.provider import ProviderError
from sharley.providers.base import HttpProvider


class AnthropicProvider(HttpProvider):
    name, family, cost_rank = "anthropic", "anthropic", 6

    def __init__(self, **kw):
        kw.setdefault("base_url", "https://api.anthropic.com")
        super().__init__(**kw)

    def complete(self, system, user, *, images=None):
        content: list | str = user
        if images:
            content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                    "data": base64.b64encode(i).decode()}} for i in images]
            content.append({"type": "text", "text": user})
        data = self._post(f"{self.base_url}/v1/messages", {
            "model": self.model, "max_tokens": 8192, "system": system,
            "messages": [{"role": "user", "content": content}],
        }, {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"})
        try:
            return "".join(b["text"] for b in data["content"] if b.get("type") == "text")
        except (KeyError, TypeError):
            raise ProviderError("anthropic response missing content") from None
