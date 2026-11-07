"""Gemini via the Interactions API. ASSUMPTION: request/response shape below; confirm against
google-genai >= 2.3.0 docs once a key is available (see OPEN_QUESTIONS.md)."""
import base64

from sharley.harness.provider import ProviderError
from sharley.providers.base import HttpProvider

THINKING_LEVELS = ("low", "medium", "high")


class GeminiProvider(HttpProvider):
    name, family = "gemini", "google"

    def __init__(self, *, thinking_level: str = "medium", **kw):
        if thinking_level not in THINKING_LEVELS:
            raise ValueError(f"thinking_level must be one of {THINKING_LEVELS}")
        kw.setdefault("base_url", "https://generativelanguage.googleapis.com/v1beta")
        kw.setdefault("timeout", 1200.0 if thinking_level == "high" else 120.0)
        super().__init__(**kw)
        self.thinking_level = thinking_level

    def complete(self, system, user, *, images=None):
        parts: list = [{"type": "text", "text": user}] + [
            {"type": "image", "mime_type": "image/png", "data": base64.b64encode(i).decode()} for i in images or []]
        # No temperature/top_p/top_k/cached_content: the model rejects them.
        data = self._post(f"{self.base_url}/interactions", {
            "model": self.model, "system_instruction": system, "input": parts,
            "generation_config": {"thinking_level": self.thinking_level},
        }, {"x-goog-api-key": self.api_key})
        try:
            return "".join(o["text"] for o in data["outputs"] if o.get("type") == "text")
        except (KeyError, TypeError):
            raise ProviderError("gemini response missing outputs") from None
