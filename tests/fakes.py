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


class EchoWriter(ModelProvider):
    """Writes one valid test per requirement id in the prompt; answers intake steps with fixed JSON."""
    name, model, family = "echo", "echo-1", "fake"

    def __init__(self, extract_reply=None, coverage_reply='{"mappings": []}'):
        self.extract_reply, self.coverage_reply = extract_reply, coverage_reply

    def health(self):
        return True

    def complete(self, system, user, *, images=None):
        import json
        import re

        if "write_functional" in system or "QA engineer" in system or "security tester" in system:
            ids = sorted(set(re.findall(r'"id":"(R\d+)"', user)))
            return json.dumps({"tests": [{"name": f"t {i}", "code": "def test_x():\n    assert True\n",
                                          "requirement_ids": [i], "hint": "something is wrong"} for i in ids]})
        if "uncovered input sentence" in system:
            return self.coverage_reply
        return self.extract_reply
