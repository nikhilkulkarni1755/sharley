"""Shared HTTP plumbing: one error type, secrets never leave in messages."""
import httpx

from sharley.harness.budget import Meter
from sharley.harness.provider import ModelProvider, ProviderError


def sniff_mime(data: bytes) -> str:
    """Real media type from magic bytes: providers reject a JPEG labelled as PNG."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:3] == b"GIF":
        return "image/gif"
    return "image/png"


class HttpProvider(ModelProvider):
    def __init__(self, *, api_key: str = "", base_url: str = "", model: str = "",
                 timeout: float = 60.0, client: httpx.Client | None = None, meter: Meter | None = None):
        self.api_key, self.base_url, self.model = api_key, base_url.rstrip("/"), model
        self.timeout, self.meter = timeout, meter
        self.client = client or httpx.Client()

    def configured(self) -> bool:
        return bool(self.api_key and self.model)

    def health(self) -> bool:
        return self.configured()

    def _redact(self, text: str) -> str:
        return text.replace(self.api_key, "***")[:300] if self.api_key else text[:300]

    def _post(self, url: str, payload: dict, headers: dict) -> dict:
        if self.meter:
            self.meter.check(self.name)
        try:
            r = self.client.post(url, json=payload, headers=headers, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.name} request failed: {self._redact(str(e))}") from None
        if r.status_code >= 300:
            raise ProviderError(f"{self.name} HTTP {r.status_code}: {self._redact(r.text)}")
        try:
            return r.json()
        except ValueError:
            raise ProviderError(f"{self.name} returned non-JSON") from None

    def _meter(self, data: dict, tokens_in: str, tokens_out: str) -> None:
        """Charge the ledger from the response's usage block (called once per successful response)."""
        if not self.meter:
            return
        u = data.get("usage") or {}
        self.meter.charge(self.name, self.model, int(u.get(tokens_in, 0)), int(u.get(tokens_out, 0)),
                          int(u.get("cache_read_input_tokens", 0)), int(u.get("cache_creation_input_tokens", 0)))
