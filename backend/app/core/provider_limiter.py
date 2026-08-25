"""Semáforo Redis: N chamadas simultâneas por provider externo."""

from __future__ import annotations

import time
import uuid
from types import TracebackType

from app.core.config import settings
from app.core.rate_limiter import RateLimitExceeded

_ACQUIRE = """
local now = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - ttl)
if redis.call('ZCARD', KEYS[1]) < tonumber(ARGV[1]) then
  redis.call('ZADD', KEYS[1], now, ARGV[2])
  redis.call('EXPIRE', KEYS[1], ttl)
  return 1
end
return 0
"""

_RELEASE = """
return redis.call('ZREM', KEYS[1], ARGV[1])
"""


class ProviderSemaphore:
    def __init__(self) -> None:
        self._redis = None
        self._acquire = None
        self._release = None

    def _client(self):
        if self._redis is None:
            import redis

            self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            self._acquire = self._redis.register_script(_ACQUIRE)
            self._release = self._redis.register_script(_RELEASE)
        return self._redis

    def _key(self, provider: str) -> str:
        return f"scenecraft:provider_sem:{provider}"

    def acquire(self, provider: str, *, timeout: float = 90.0, poll_seconds: float = 0.25) -> str:
        if not provider:
            return ""
        limit = settings.provider_concurrency_for(provider)
        token = str(uuid.uuid4())
        ttl = int(max(timeout * 2, 60))
        deadline = time.monotonic() + timeout
        if self._acquire is None:
            self._client()
        while True:
            ok = int(
                self._acquire(
                    keys=[self._key(provider)],
                    args=[limit, token, time.time(), ttl],
                )
            )
            if ok:
                return token
            if time.monotonic() >= deadline:
                raise RateLimitExceeded(provider)
            time.sleep(poll_seconds)

    def release(self, provider: str, token: str) -> None:
        if not provider or not token:
            return
        if self._release is None:
            self._client()
        self._release(keys=[self._key(provider)], args=[token])

    def hold(self, provider: str | None, **kwargs):
        return _ProviderSlot(self, provider, **kwargs)


class _ProviderSlot:
    def __init__(self, sem: ProviderSemaphore, provider: str | None, **kwargs):
        self._sem = sem
        self._provider = provider or ""
        self._kwargs = kwargs
        self._token = ""

    def __enter__(self) -> str:
        if self._provider:
            self._token = self._sem.acquire(self._provider, **self._kwargs)
        return self._token

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._provider:
            self._sem.release(self._provider, self._token)


provider_semaphore = ProviderSemaphore()
