"""Shared HTTP plumbing: one error type, secrets never leave in messages."""
import httpx

from sharley.harness.provider import ModelProvider, ProviderError


class HttpProvider(ModelProvider):
    def __init__(self, *, api_key: str = "", base_url: str = "", model: str = "",
                 timeout: float = 60.0, client: httpx.Client | None = None):
        self.api_key, self.base_url, self.model = api_key, base_url.rstrip("/"), model
        self.timeout = timeout
        self.client = client or httpx.Client()

    def configured(self) -> bool:
        return bool(self.api_key and self.model)

    def health(self) -> bool:
        return self.configured()

    def _redact(self, text: str) -> str:
        return text.replace(self.api_key, "***")[:300] if self.api_key else text[:300]

    def _post(self, url: str, payload: dict, headers: dict) -> dict:
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
