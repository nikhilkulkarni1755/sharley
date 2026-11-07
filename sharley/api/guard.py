"""Public-deployment guard: paid model endpoints need an admin key; judging runs are rate-limited and capped."""
import secrets
import threading
import time
from collections import defaultdict, deque
from collections.abc import Mapping

from fastapi import HTTPException, Request


class Guard:
    def __init__(self, public: bool = False, admin_key: str = "", runs_per_minute: int = 20, max_concurrent: int = 3):
        self.public, self.admin_key = public, admin_key
        self.runs_per_minute, self.max_concurrent = runs_per_minute, max_concurrent
        self._hits: dict[str, deque] = defaultdict(deque)
        self._active = 0
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Guard":
        return cls(public=env.get("SHARLEY_PUBLIC_MODE", "0").lower() in ("1", "true", "yes"), admin_key=env.get("SHARLEY_ADMIN_KEY", ""),
                   runs_per_minute=int(env.get("SHARLEY_RUNS_PER_MINUTE", "20")), max_concurrent=int(env.get("SHARLEY_MAX_CONCURRENT_RUNS", "3")))

    def require_admin(self, request: Request) -> None:
        """Endpoints that spend model tokens. Open in local mode; in public mode they need the admin key header."""
        if not self.public:
            return
        given = request.headers.get("x-sharley-key", "")
        if not self.admin_key or not secrets.compare_digest(given, self.admin_key):
            raise HTTPException(status_code=403, detail="this endpoint needs an admin key on the public deployment")

    @staticmethod
    def client_ip(request: Request) -> str:
        return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")

    def acquire_run(self, request: Request) -> None:
        """Per-IP sliding window plus a global cap on concurrent sandboxes. Pair every success with release_run()."""
        now, ip = time.monotonic(), self.client_ip(request)
        with self._lock:
            hits = self._hits[ip]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= self.runs_per_minute:
                raise HTTPException(status_code=429, detail="too many runs from your address; wait a minute and retry")
            if self._active >= self.max_concurrent:
                raise HTTPException(status_code=429, detail="the judge is busy; retry in a few seconds")
            hits.append(now)
            self._active += 1

    def release_run(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)
