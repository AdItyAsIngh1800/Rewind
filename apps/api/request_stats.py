"""The API's own request latency and error rate over a recent window (spec §N).

Observed in the API process, because only the process serving requests sees them. A
rolling five-minute window rather than totals since start: "the API is failing now" is
the question System Health answers, and a lifetime rate would hide a fresh outage under
hours of healthy traffic. ``None`` when no request arrived in the window, never zero.

ponytail: one process, in memory; with several API replicas each reports its own, and a
shared store (Redis) is the upgrade if the API is ever scaled out.
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field

WINDOW_S = 300.0


@dataclass
class RequestWindow:
    """Recent requests as (arrival, status code, duration in seconds)."""

    window_s: float = WINDOW_S
    _requests: deque[tuple[float, int, float]] = field(default_factory=deque)

    def record(self, status_code: int, duration_s: float, now: float | None = None) -> None:
        """Add one finished request and forget those older than the window."""
        stamp = time.monotonic() if now is None else now
        self._requests.append((stamp, status_code, duration_s))
        self._expire(stamp)

    def clear(self) -> None:
        """Forget every recorded request; for tests that measure from a known start."""
        self._requests.clear()

    def _expire(self, now: float) -> None:
        while self._requests and self._requests[0][0] < now - self.window_s:
            self._requests.popleft()

    def error_rate(self, now: float | None = None) -> float | None:
        """Share of requests in the window that failed on the server (5xx)."""
        self._expire(time.monotonic() if now is None else now)
        if not self._requests:
            return None
        return sum(1 for _, code, _ in self._requests if code >= 500) / len(self._requests)

    def latency_p95_ms(self, now: float | None = None) -> float | None:
        """Return the 95th-percentile request duration in the window, in milliseconds."""
        self._expire(time.monotonic() if now is None else now)
        if not self._requests:
            return None
        durations = sorted(d for _, _, d in self._requests)
        return durations[math.ceil(0.95 * len(durations)) - 1] * 1000


requests = RequestWindow()
