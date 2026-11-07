import threading

import pytest

from sharley.storage import JsonRepository, MongoRepository, open_repository


class FakeCollection:
    def __init__(self):
        self.docs = {}

    def replace_one(self, flt, doc, upsert=False):
        self.docs[flt["_id"]] = dict(doc)

    def find_one(self, flt):
        return dict(self.docs[flt["_id"]]) if flt["_id"] in self.docs else None

    def find(self, flt):
        return [dict(d) for d in self.docs.values() if all(d.get(k) == v for k, v in flt.items())]

    def delete_one(self, flt):
        n = 1 if self.docs.pop(flt["_id"], None) is not None else 0
        return type("R", (), {"deleted_count": n})()

    def find_one_and_update(self, flt, upd, return_document=True):
        for d in self.docs.values():
            if all(d.get(k) == v for k, v in flt.items()):
                d.update(upd["$set"])
                return dict(d)
        return None


class FakeDb(dict):
    def __missing__(self, k):
        self[k] = FakeCollection()
        return self[k]


@pytest.fixture(params=["json", "mongo"])
def repo(request, tmp_path):
    return JsonRepository(tmp_path) if request.param == "json" else MongoRepository(FakeDb())


# ---- same contract for both backends
def test_put_get_roundtrip_hides_internal_ids(repo):
    repo.put("specs", "s1", {"a": 1})
    assert repo.get("specs", "s1") == {"a": 1}
    assert repo.get("specs", "missing") is None


def test_put_overwrites(repo):
    repo.put("verdicts", "v", {"a": 1})
    repo.put("verdicts", "v", {"a": 2})
    assert repo.get("verdicts", "v") == {"a": 2}


def test_find_filters_by_equality(repo):
    repo.put("mutants", "m1", {"split": "train"})
    repo.put("mutants", "m2", {"split": "heldout"})
    assert repo.find("mutants", split="heldout") == [{"split": "heldout"}]
    assert len(repo.find("mutants")) == 2


def test_delete_reports_existence(repo):
    repo.put("runs", "r", {})
    assert repo.delete("runs", "r") is True and repo.delete("runs", "r") is False


def test_queue_claim_is_fifo_and_exactly_once(repo):
    repo.put("queue", "t1", {"status": "pending", "n": 1})
    repo.put("queue", "t2", {"status": "pending", "n": 2})
    assert repo.claim("queue")[0] == "t1"
    assert repo.claim("queue")[0] == "t2"
    assert repo.claim("queue") is None
    assert repo.get("queue", "t1")["status"] == "claimed"


@pytest.mark.parametrize("bad", ["../etc/passwd", "users", "", "specs/../x", "$where"])
def test_unknown_collections_rejected(repo, bad):
    with pytest.raises(ValueError):
        repo.put(bad, "x", {})


# ---- json specifics
def test_json_hostile_doc_ids_cannot_escape_root(tmp_path):
    root = tmp_path / "store"
    r = JsonRepository(root)
    r.put("specs", "../../evil", {"a": 1})
    assert r.get("specs", "../../evil") == {"a": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["store"]


def test_json_persists_across_instances(tmp_path):
    JsonRepository(tmp_path).put("specs", "s", {"v": 1})
    assert JsonRepository(tmp_path).get("specs", "s") == {"v": 1}


def test_json_concurrent_claims_never_double_assign(tmp_path):
    r = JsonRepository(tmp_path)
    for i in range(20):
        r.put("queue", f"t{i}", {"status": "pending"})
    got, lock = [], threading.Lock()

    def worker():
        while (c := r.claim("queue")):
            with lock:
                got.append(c[0])

    threads = [threading.Thread(target=worker) for _ in range(5)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(got) == sorted(f"t{i}" for i in range(20))


# ---- factory fallback
def test_factory_uses_json_without_uri(tmp_path):
    assert isinstance(open_repository({"SHARLEY_HOME": str(tmp_path)}), JsonRepository)


def test_factory_falls_back_when_mongo_unreachable(tmp_path):
    def boom(uri):
        raise RuntimeError("no route")

    env = {"MONGODB_URI": "mongodb://x", "SHARLEY_HOME": str(tmp_path)}
    assert isinstance(open_repository(env, boom), JsonRepository)


def test_factory_uses_mongo_when_ping_succeeds(tmp_path):
    class Client:
        admin = type("A", (), {"command": staticmethod(lambda c: {"ok": 1})})()

        def __getitem__(self, n):
            return FakeDb()

    env = {"MONGODB_URI": "mongodb://x", "SHARLEY_HOME": str(tmp_path)}
    assert isinstance(open_repository(env, lambda u: Client()), MongoRepository)


def test_offline_flag_skips_mongo_even_if_configured(tmp_path):
    called = []
    env = {"MONGODB_URI": "mongodb://x", "SHARLEY_OFFLINE": "1", "SHARLEY_HOME": str(tmp_path)}
    assert isinstance(open_repository(env, lambda u: called.append(u)), JsonRepository) and not called
