"""The worker heartbeat is read the way ARQ writes it."""

from __future__ import annotations

from apps.api.queue import read_heartbeat


def test_heartbeat_age_and_counters_come_from_the_arq_line() -> None:
    """A key with 21 s of a 31 s TTL left was written 10 s ago; counters are read by name."""
    line = "Sep-14 10:00:00 j_complete=4 j_failed=1 j_retried=2 j_ongoing=0 queued=3"
    assert read_heartbeat(line, ttl_ms=21_000, interval_s=30) == (10.0, 2, 1)
