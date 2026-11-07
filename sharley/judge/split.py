"""Deterministic example/sealed split (the LeetCode model)."""
from sharley.hashing import sha256_text
from sharley.schemas import TestBank, TestCase


def _rank(seed: int, test: TestCase) -> str:
    return sha256_text(f"{seed}:{test.id}")


def split_bank(tests: list[TestCase], spec_hash: str, seed: int, ratio: float = 0.3) -> TestBank:
    """~ratio of each family become examples; every family keeps at least one sealed test."""
    example_ids: set[str] = set()
    for family in {t.family for t in tests}:
        group = sorted((t for t in tests if t.family == family), key=lambda t: _rank(seed, t))
        n = min(round(len(group) * ratio), len(group) - 1)
        example_ids |= {t.id for t in group[:max(n, 0)]}
    if not example_ids and len(tests) > 1:  # all-singleton families: still show the implementer one example
        example_ids = {min(tests, key=lambda t: _rank(seed, t)).id}
    tagged = [t.model_copy(update={"visibility": "example" if t.id in example_ids else "sealed"}) for t in tests]
    return TestBank(spec_hash=spec_hash, seed=seed, example_ratio=ratio, tests=tagged)


def ordered_sealed(bank: TestBank) -> list[TestCase]:
    """Stable shuffled order so 'sealed test 37 of 58' reveals nothing about requirement order."""
    return sorted(bank.sealed, key=lambda t: _rank(bank.seed, t))
