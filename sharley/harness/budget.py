"""Spend guard: every paid call is metered into a persistent ledger and refused once the cap is reached."""
import json
import os
import tempfile
import threading
from collections.abc import Mapping
from pathlib import Path

from sharley.harness.provider import ProviderError

# USD per million tokens (input, output). Unknown models are priced conservatively so spend is over-, never under-estimated.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50),
    "claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0), "claude-fable-5-1": (10.0, 50.0),
}
UNKNOWN_PRICE = (10.0, 50.0)
CACHE_READ, CACHE_WRITE = 0.1, 1.25  # multipliers on the input price
LOCAL_PROVIDERS = {"local"}


class BudgetExceeded(ProviderError):
    pass


class Meter:
    def __init__(self, ledger: Path, limit_usd: float, prices: Mapping[str, tuple[float, float]] | None = None):
        self.ledger, self.limit = Path(ledger), limit_usd
        self.prices = {**PRICES, **(prices or {})}
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Meter":
        extra = {}
        if env.get("META_PRICE_IN") and env.get("META_PRICE_OUT") and env.get("META_MODEL"):
            extra[env["META_MODEL"]] = (float(env["META_PRICE_IN"]), float(env["META_PRICE_OUT"]))
        return cls(Path(env.get("SHARLEY_HOME", ".sharley")) / "ledger.json", float(env.get("SHARLEY_BUDGET_USD", "15")), extra)

    def _read(self) -> dict:
        try:
            return json.loads(self.ledger.read_text())
        except (OSError, ValueError):
            return {"total_usd": 0.0, "by_provider": {}, "calls": 0}

    def _write(self, data: dict) -> None:
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.ledger.parent)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp, self.ledger)

    def spent(self) -> float:
        with self._lock:
            return self._read()["total_usd"]

    def check(self, provider: str) -> None:
        """Call before every paid request."""
        if provider not in LOCAL_PROVIDERS and self.spent() >= self.limit:
            raise BudgetExceeded(f"spend cap reached (${self.spent():.2f} of ${self.limit:.2f}); raise SHARLEY_BUDGET_USD to continue")

    def cost(self, model: str, tokens_in: int, tokens_out: int, cache_read: int = 0, cache_write: int = 0) -> float:
        pin, pout = self.prices.get(model, UNKNOWN_PRICE)
        return (tokens_in * pin + cache_read * pin * CACHE_READ + cache_write * pin * CACHE_WRITE + tokens_out * pout) / 1e6

    def charge(self, provider: str, model: str, tokens_in: int, tokens_out: int, cache_read: int = 0, cache_write: int = 0) -> float:
        usd = 0.0 if provider in LOCAL_PROVIDERS else self.cost(model, tokens_in, tokens_out, cache_read, cache_write)
        with self._lock:
            d = self._read()
            d["total_usd"] = round(d["total_usd"] + usd, 6)
            d["calls"] += 1
            p = d["by_provider"].setdefault(provider, {"usd": 0.0, "in": 0, "out": 0})
            p["usd"] = round(p["usd"] + usd, 6)
            p["in"] += tokens_in + cache_read + cache_write
            p["out"] += tokens_out
            self._write(d)
        return usd
