"""Repository interface over the collections Sharley persists."""
from abc import ABC, abstractmethod

COLLECTIONS = ("specs", "test_banks", "runs", "verdicts", "mutants", "skill_versions", "queue")


class Repository(ABC):
    @staticmethod
    def check_collection(name: str) -> str:
        if name not in COLLECTIONS:
            raise ValueError(f"unknown collection {name!r}")
        return name

    @abstractmethod
    def put(self, collection: str, doc_id: str, doc: dict) -> None: ...

    @abstractmethod
    def get(self, collection: str, doc_id: str) -> dict | None: ...

    @abstractmethod
    def find(self, collection: str, **equals) -> list[dict]: ...

    @abstractmethod
    def delete(self, collection: str, doc_id: str) -> bool: ...

    @abstractmethod
    def claim(self, collection: str) -> tuple[str, dict] | None:
        """Atomically flip one status=='pending' doc to 'claimed' and return it (queue pull)."""
