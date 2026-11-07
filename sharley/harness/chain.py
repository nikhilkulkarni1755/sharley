"""Ordered fallback chain with startup health checks and tier routing."""
import logging

from sharley.harness.provider import ModelProvider, ProviderError, Tier
from sharley.schemas import ModelRef

log = logging.getLogger("sharley.chain")


class AllProvidersFailed(ProviderError):
    pass


class FallbackChain:
    def __init__(self, providers: list[ModelProvider]):
        if not providers:
            raise ValueError("a chain needs at least one provider")
        self.providers = providers
        self.healthy: dict[str, bool] = {}
        self.active: str | None = None

    def check(self) -> dict[str, bool]:
        """Run health checks once (call at startup) and remember the results."""
        self.healthy = {p.name: bool(p.health()) for p in self.providers}
        for name, ok in self.healthy.items():
            log.info("provider %s healthy=%s", name, ok)
        return self.healthy

    def candidates(self, tier: Tier = "strong") -> list[ModelProvider]:
        live = [p for p in self.providers if self.healthy.get(p.name, True)]
        return sorted(live, key=lambda p: p.cost_rank) if tier == "fast" else live

    def complete(self, system: str, user: str, *, tier: Tier = "strong", images: list[bytes] | None = None) -> str:
        errors = []
        for p in self.candidates(tier):
            try:
                out = p.complete(system, user, images=images)
            except ProviderError as e:
                log.warning("provider %s failed: %s", p.name, e)
                errors.append(f"{p.name}: {e}")
                continue
            self.active = p.name
            return out
        raise AllProvidersFailed("; ".join(errors) or "no healthy providers")

    def active_ref(self) -> ModelRef:
        """Identity of the provider that last answered (or the first healthy one before any call)."""
        p = next((p for p in self.providers if p.name == self.active), None) or next(iter(self.candidates()), self.providers[0])
        return ModelRef(provider=p.name, model=p.model, family=p.family)
