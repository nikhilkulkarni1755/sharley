"""Sealed banks live in the repository (outside any implementer workspace)."""
from sharley.schemas import TestBank
from sharley.storage.repository import Repository


def bank_key(bank: TestBank) -> str:
    return f"{bank.spec_hash}:{bank.seed}"


def save_bank(repo: Repository, bank: TestBank) -> str:
    repo.put("test_banks", bank_key(bank), bank.model_dump())
    return bank_key(bank)


def load_bank(repo: Repository, key: str) -> TestBank:
    doc = repo.get("test_banks", key)
    if doc is None:
        raise KeyError(f"no test bank {key!r}")
    return TestBank.model_validate(doc)
