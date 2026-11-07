"""Public projections of banks: examples in full, sealed tests as opaque locked tiles."""
from sharley.judge import ordered_sealed
from sharley.schemas import TestBank


def bank_view(bank: TestBank) -> dict:
    return {
        "key": f"{bank.spec_hash}:{bank.seed}",
        "spec_hash": bank.spec_hash,
        "seed": bank.seed,
        "author": bank.author.model_dump() if bank.author else None,
        "examples": [{"id": t.id, "name": t.name, "family": t.family, "requirement_ids": t.requirement_ids,
                      "file": t.file, "code": t.code} for t in bank.examples],
        # sealed tests expose only their position, family and a lock: never code, file, name or hint
        "sealed": [{"index": i, "family": t.family, "locked": True} for i, t in enumerate(ordered_sealed(bank), 1)],
    }
