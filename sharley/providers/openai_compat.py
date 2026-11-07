"""OpenAI-compatible chat endpoint: serves Meta, SubQ and the local vLLM/Ollama fallback."""
import base64

from sharley.harness.provider import ProviderError
from sharley.providers.base import HttpProvider


class OpenAICompatProvider(HttpProvider):
    def __init__(self, name: str, family: str, *, cost_rank: int = 5, requires_key: bool = True, **kw):
        super().__init__(**kw)
        self.name, self.family, self.cost_rank, self.requires_key = name, family, cost_rank, requires_key

    def configured(self) -> bool:
        return bool(self.base_url and self.model and (self.api_key or not self.requires_key))

    def health(self) -> bool:
        if not self.configured():
            return False
        if self.requires_key:
            return True
        try:  # local endpoints are cheap to probe
            return self.client.get(f"{self.base_url}/models", timeout=3).status_code < 300
        except Exception:
            return False

    def complete(self, system, user, *, images=None):
        content: list | str = user
        if images:
            content = [{"type": "text", "text": user}] + [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(i).decode()}}
                for i in images]
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        data = self._post(f"{self.base_url}/chat/completions", {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
        }, headers)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError(f"{self.name} response missing choices[0].message.content") from None
