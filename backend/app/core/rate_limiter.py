"""Rate limiter Redis (janela fixa) para workers e providers."""

from __future__ import annotations

import time

import redis

from app.core.config import settings
from app.core.queues import JobQueue

_INCR_EXPIRE = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


class RateLimitExceeded(Exception):
    def __init__(self, key: str):
        super().__init__(f"rate limit exceeded: {key}")
        self.key = key


class RateLimiter:
    def __init__(self) -> None:
        self._redis: redis.Redis | None = None
        self._script = None

    def _client(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            self._script = self._redis.register_script(_INCR_EXPIRE)
        return self._redis

    def _bucket_key(self, name: str) -> str:
        window = settings.rate_limit_window_seconds
        slot = int(time.time()) // window
        return f"scenecraft:ratelimit:{name}:{slot}"

    def try_acquire(self, name: str, limit: int) -> bool:
        self._client()
        current = int(self._script(keys=[self._bucket_key(name)], args=[settings.rate_limit_window_seconds]))
        return current <= limit

    def acquire(
        self,
        queue: JobQueue | str,
        *,
        timeout: float = 60.0,
        poll_seconds: float = 0.4,
    ) -> None:
        name = queue.value if isinstance(queue, JobQueue) else queue
        limit = settings.rate_limit_for(name)
        deadline = time.monotonic() + timeout
        while True:
            if self.try_acquire(name, limit):
                return
            if time.monotonic() >= deadline:
                raise RateLimitExceeded(name)
            time.sleep(poll_seconds)


limiter = RateLimiter()
