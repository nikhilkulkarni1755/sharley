"""MongoDB repository (Atlas or a local container). Takes a pymongo Database."""
from sharley.storage.repository import Repository


class MongoRepository(Repository):
    def __init__(self, db):
        self.db = db

    def _c(self, collection: str):
        return self.db[self.check_collection(collection)]

    @staticmethod
    def _clean(doc: dict | None) -> dict | None:
        return None if doc is None else {k: v for k, v in doc.items() if k != "_id"}

    def put(self, collection, doc_id, doc):
        self._c(collection).replace_one({"_id": doc_id}, {**doc, "_id": doc_id}, upsert=True)

    def get(self, collection, doc_id):
        return self._clean(self._c(collection).find_one({"_id": doc_id}))

    def find(self, collection, **equals):
        return [self._clean(d) for d in self._c(collection).find(equals)]

    def delete(self, collection, doc_id):
        return self._c(collection).delete_one({"_id": doc_id}).deleted_count > 0

    def claim(self, collection):
        doc = self._c(collection).find_one_and_update(
            {"status": "pending"}, {"$set": {"status": "claimed"}}, return_document=True)
        return None if doc is None else (doc["_id"], self._clean(doc))
