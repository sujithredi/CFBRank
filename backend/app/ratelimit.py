"""
A small in-process, per-client sliding-window rate limiter.

This is defense in depth for the expensive endpoints (see app/routers/odds.py), not a
replacement for limiting at the reverse proxy or CDN:

* State lives in one process. With N uvicorn workers a client can make up to N times
  the configured limit, because each worker counts separately.
* The client key is `request.client.host`. Behind a proxy that is the proxy's address
  unless uvicorn is started with `--proxy-headers --forwarded-allow-ips=<proxy ip>`
  (see docs/SETUP.md). X-Forwarded-For is deliberately NOT parsed here: any client can
  send that header, so trusting it would let an attacker pick their own bucket.

Memory is bounded: at most `max_tracked_clients` keys are remembered, and each key keeps
at most `max_requests` timestamps.
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict, deque
from typing import Callable

from fastapi import HTTPException, Request


class RateLimiter:
    """Allow at most `max_requests` per `window_seconds` for each key. 0 requests = disabled."""

    def __init__(
        self,
        max_requests: int,
        window_seconds: float = 60.0,
        max_tracked_clients: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_requests = max(0, int(max_requests))
        self.window_seconds = float(window_seconds)
        self.max_tracked_clients = max(1, int(max_tracked_clients))
        self._clock = clock
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.max_requests > 0

    def check(self, key: str) -> tuple[bool, float]:
        """
        Record one request from `key`.

        Returns (allowed, retry_after_seconds). A rejected request is not recorded, so a
        client that keeps retrying is let back in as soon as its oldest hit expires.
        """
        if not self.enabled:
            return True, 0.0

        now = self._clock()
        cutoff = now - self.window_seconds
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                self._make_room(now)  # before adding, so the new client is never the one dropped
                hits = self._hits[key] = deque()
            else:
                self._hits.move_to_end(key)

            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= self.max_requests:
                return False, max(0.0, hits[0] + self.window_seconds - now)

            hits.append(now)
            return True, 0.0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def _make_room(self, now: float) -> None:
        """Called with the lock held, before a new key is added: leave space for exactly one more."""
        if len(self._hits) < self.max_tracked_clients:
            return
        cutoff = now - self.window_seconds
        # First drop clients whose every hit has expired, then the least recently seen.
        for stale in [k for k, h in self._hits.items() if not h or h[-1] <= cutoff]:
            del self._hits[stale]
        while len(self._hits) >= self.max_tracked_clients:
            self._hits.popitem(last=False)


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def enforce(limiter: RateLimiter, request: Request) -> None:
    """Raise HTTP 429 (with Retry-After) when `request`'s client is over `limiter`'s limit."""
    allowed, retry_after = limiter.check(client_key(request))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests; please slow down and retry shortly.",
            headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
        )
