"""API latency and error rate over a rolling window."""

from __future__ import annotations

from apps.api.request_stats import RequestWindow


def test_no_requests_is_not_measured_rather_than_zero() -> None:
    """An idle API has no error rate, which is different from a rate of zero."""
    window = RequestWindow()
    assert window.error_rate(now=0.0) is None and window.latency_p95_ms(now=0.0) is None


def test_only_server_errors_count_as_errors() -> None:
    """A 404 is the client's mistake; a 500 is the API's."""
    window = RequestWindow()
    for code in (200, 200, 404, 500):
        window.record(code, 0.01, now=10.0)
    assert window.error_rate(now=10.0) == 0.25


def test_requests_older_than_the_window_are_forgotten() -> None:
    """An outage an hour ago does not colour the rate now."""
    window = RequestWindow(window_s=300.0)
    window.record(500, 0.01, now=0.0)
    window.record(200, 0.01, now=400.0)
    assert window.error_rate(now=400.0) == 0.0


def test_p95_latency_is_the_slow_tail_not_the_mean() -> None:
    """One slow request in twenty is the 95th percentile's business."""
    window = RequestWindow()
    for _ in range(19):
        window.record(200, 0.010, now=1.0)
    window.record(200, 2.0, now=1.0)
    assert window.latency_p95_ms(now=1.0) == 10.0
    window.record(200, 2.0, now=1.0)
    assert window.latency_p95_ms(now=1.0) == 2000.0
