"""open_repository: Mongo when reachable, JSON files otherwise."""
import logging
from collections.abc import Mapping

from sharley.providers.registry import is_offline
from sharley.storage.json_store import JsonRepository
from sharley.storage.mongo_store import MongoRepository
from sharley.storage.repository import COLLECTIONS, Repository

log = logging.getLogger("sharley.storage")


def open_repository(env: Mapping[str, str], mongo_client_factory=None) -> Repository:
    uri = env.get("MONGODB_URI", "")
    if uri and not is_offline(env):
        try:
            if mongo_client_factory is None:
                from pymongo import MongoClient

                mongo_client_factory = lambda u: MongoClient(u, serverSelectionTimeoutMS=2000)  # noqa: E731
            client = mongo_client_factory(uri)
            client.admin.command("ping")
            return MongoRepository(client["sharley"])
        except Exception as e:  # any failure -> fall back, never block the demo
            log.warning("MongoDB unavailable (%s); using JSON store", type(e).__name__)
    return JsonRepository(env.get("SHARLEY_HOME", ".sharley"))


__all__ = ["COLLECTIONS", "JsonRepository", "MongoRepository", "Repository", "open_repository"]
