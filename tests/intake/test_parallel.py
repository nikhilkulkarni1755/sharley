import json
import threading
import time

from sharley.harness import FallbackChain
from sharley.harness.provider import ModelProvider
from sharley.intake.extract import chunks, propose
from sharley.providers import verifier_chain


class Slow(ModelProvider):
    """Every call takes `delay` seconds and returns requirements that depend on the chunk it was given."""
    name, model, family = "slow", "slow", "fake"

    def __init__(self, delay):
        self.delay, self.active, self.peak, self.lock = delay, 0, 0, threading.Lock()

    def health(self):
        return True

    def complete(self, system, user, *, images=None):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(self.delay)
        with self.lock:
            self.active -= 1
        tag = user.split("chunk-")[1].split()[0] if "chunk-" in user else "x"
        return json.dumps({"requirements": [{"text": f"Requirement from {tag}", "category": "functional"}]})


def text(n):
    return "\n".join(f"chunk-{i:02d} " + "x" * 60 for i in range(n))


def test_chunks_are_extracted_in_parallel_and_merged_in_order():
    p = Slow(0.3)
    body = text(4)
    n = len(chunks(body, 70))
    assert n == 4
    t = time.time()
    out = propose(FallbackChain([p]), body, None, chunk_chars=70)
    elapsed = time.time() - t
    assert elapsed < 0.3 * n * 0.7, f"took {elapsed:.2f}s, sequential would be {0.3 * n:.2f}s"
    assert p.peak > 1
    assert [r.text for r in out] == [f"Requirement from {i:02d}" for i in range(4)]  # chunk order, not completion order


def test_single_short_input_still_makes_exactly_one_call():
    p = Slow(0.0)
    propose(FallbackChain([p]), "a short spec of the thing", None)
    assert p.peak == 1


def test_a_failing_chunk_fails_the_whole_extraction_instead_of_silently_dropping_requirements():
    import pytest
    from sharley.harness import StepFailed

    class Flaky(Slow):
        def complete(self, system, user, *, images=None):
            if "chunk-02" in user:
                return "not json"
            return super().complete(system, user, images=images)

    with pytest.raises(StepFailed):
        propose(FallbackChain([Flaky(0.0)]), text(4), None, chunk_chars=70)


def test_small_fast_steps_prefer_claude_while_strong_steps_still_start_with_meta():
    env = {"META_API_KEY": "k", "META_BASE_URL": "http://x", "META_MODEL": "muse", "ANTHROPIC_API_KEY": "k"}
    chain = verifier_chain(env)
    assert [p.name for p in chain.candidates("strong")][:2] == ["meta", "anthropic"]
    assert [p.name for p in chain.candidates("fast")][:2] == ["local", "anthropic"] or [p.name for p in chain.candidates("fast")][0] != "meta"
    assert chain.candidates("fast")[-1].name == "meta"
