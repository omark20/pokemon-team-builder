"""Per-address request limits, counted in this process in fixed windows.

Counting in memory is exact because the service runs one process. Each bucket's table
starts empty with every new window, so it cannot grow without bound. Over the limit is a
429 whose Retry-After header gives the seconds until the window ends, and one warning
line per address per bucket per window, so a script being refused cannot flood the log.
"""

import logging
import math
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from fastapi import HTTPException, Request

from app.logs import log_event, route_template

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Limit:
    requests: int
    window_seconds: float


LIMITS = {
    "read": Limit(600, 60),  # every GET under /api, checked before any cookie or database work
    "write": Limit(120, 60),  # team and alert writes
    "new_visitor": Limit(20, 3600),  # visitor records created, one per first team
}


@dataclass(frozen=True)
class Refusal:
    retry_after: int  # whole seconds until the window ends
    first: bool  # the first refusal for this address in this window, so it is logged


@dataclass
class _Window:
    started: float
    counts: dict[str, int] = field(default_factory=dict)
    refused: set[str] = field(default_factory=set)


class RateLimiter:
    """Counts requests per bucket and address; `hit` says whether one more is allowed."""

    def __init__(
        self, limits: Mapping[str, Limit] = LIMITS, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._limits = limits
        self._clock = clock
        self._lock = threading.Lock()
        self._windows = {bucket: _Window(clock()) for bucket in limits}

    def hit(self, bucket: str, address: str) -> Refusal | None:
        """Count one request; None if it is allowed, otherwise the refusal."""
        limit = self._limits[bucket]
        with self._lock:
            now = self._clock()
            window = self._windows[bucket]
            if now >= window.started + limit.window_seconds:
                window = self._windows[bucket] = _Window(now)
            window.counts[address] = window.counts.get(address, 0) + 1
            if window.counts[address] <= limit.requests:
                return None
            first = address not in window.refused
            window.refused.add(address)
            return Refusal(math.ceil(window.started + limit.window_seconds - now), first)


def client_address(request: Request) -> str:
    """The address a visitor is counted under. The one place that decides it."""
    return request.client.host if request.client else "unknown"


def enforce(request: Request, bucket: str) -> None:
    """Raise a 429 if the caller's address is over the bucket's limit."""
    refusal = request.app.state.limiter.hit(bucket, client_address(request))
    if refusal is None:
        return
    if refusal.first:
        log_event(
            logger,
            logging.WARNING,
            "rate_limited",
            request_id=request.state.request_id,
            route=route_template(request),
            bucket=bucket,
        )
    headers = {"Retry-After": str(refusal.retry_after)}
    raise HTTPException(429, "Too many requests", headers=headers)


def limit_reads(request: Request) -> None:
    """App-wide dependency: every GET under /api counts against the read bucket."""
    if request.method == "GET" and request.url.path.startswith("/api/"):
        enforce(request, "read")


def limit_writes(request: Request) -> None:
    """Route dependency for the visitor's own writes: teams, and dismissing alerts."""
    enforce(request, "write")
