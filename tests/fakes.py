"""Scriptable provider for tests."""
from sharley.harness.provider import ModelProvider, ProviderError


class ScriptedProvider(ModelProvider):
    def __init__(self, name="fake", replies=(), *, family="fake", healthy=True, cost_rank=5):
        self.name, self.model, self.family = name, f"{name}-m", family
        self.cost_rank, self._healthy = cost_rank, healthy
        self.replies, self.calls = list(replies), []

    def health(self):
        return self._healthy

    def complete(self, system, user, *, images=None):
        self.calls.append((system, user, images))
        if not self.replies:
            raise ProviderError("no scripted reply")
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
