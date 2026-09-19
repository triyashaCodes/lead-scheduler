import math
import threading
import time
from collections import deque
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.core.config import get_settings


class RateLimiter:
    """A sliding-window limiter kept in this process's memory.

    Good enough to blunt abuse on a single instance. With several instances,
    or behind a proxy that hides client addresses, the limit has to move to
    the proxy or a shared store such as Redis.
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._clock = clock
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> int | None:
        """Record a request. Returns None if allowed, else seconds to wait."""
        now = self._clock()
        cutoff = now - self._window
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self._max:
                return max(1, math.ceil(hits[0] + self._window - now))
            hits.append(now)
            self._prune(cutoff)
            return None

    def _prune(self, cutoff: float) -> None:
        # Keep memory bounded when many distinct addresses show up.
        if len(self._hits) <= self._max_keys:
            return
        for key in [k for k, h in self._hits.items() if not h or h[-1] <= cutoff]:
            del self._hits[key]
        while len(self._hits) > self._max_keys:
            del self._hits[next(iter(self._hits))]


@lru_cache
def get_submission_limiter() -> RateLimiter:
    settings = get_settings()
    return RateLimiter(
        settings.submission_rate_limit, settings.submission_rate_window_seconds
    )


def limit_submissions(
    request: Request,
    limiter: Annotated[RateLimiter, Depends(get_submission_limiter)],
) -> None:
    """Dependency for the public form: too many requests from one address is a 429."""
    client = request.client.host if request.client else "unknown"
    retry_after = limiter.check(client)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many submissions. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
