"""JSON-file repository: the always-available fallback."""
import json
import os
import tempfile
import threading
from pathlib import Path

from sharley.storage.repository import Repository


class JsonRepository(Repository):
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, collection: str) -> Path:
        return self.root / f"{self.check_collection(collection)}.json"

    def _load(self, collection: str) -> dict[str, dict]:
        p = self._path(collection)
        return json.loads(p.read_text()) if p.exists() else {}

    def _save(self, collection: str, data: dict) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.root)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, sort_keys=True)
        os.replace(tmp, self._path(collection))  # atomic: readers never see half a file

    def put(self, collection, doc_id, doc):
        with self._lock:
            data = self._load(collection)
            data[doc_id] = doc
            self._save(collection, data)

    def get(self, collection, doc_id):
        with self._lock:
            return self._load(collection).get(doc_id)

    def find(self, collection, **equals):
        with self._lock:
            return [d for d in self._load(collection).values() if all(d.get(k) == v for k, v in equals.items())]

    def delete(self, collection, doc_id):
        with self._lock:
            data = self._load(collection)
            if doc_id not in data:
                return False
            del data[doc_id]
            self._save(collection, data)
            return True

    def claim(self, collection):
        with self._lock:
            data = self._load(collection)
            for doc_id, doc in data.items():
                if doc.get("status") == "pending":
                    doc["status"] = "claimed"
                    self._save(collection, data)
                    return doc_id, dict(doc)
            return None
