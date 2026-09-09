"""Tests for the benchmark harness.

The self-check — scoring the golden fixtures against themselves — returns 1.0
everywhere. On its own that proves nothing: a harness hard-coded to return 1.0 would
pass it too. So these tests deliberately damage the predictions and assert that the
right metric degrades, which is the only way "all metrics pass" means anything.
"""

from __future__ import annotations

import json
import pathlib
import shutil
from collections.abc import Callable
from typing import Any

import pytest

from packages.evaluation.benchmark import BenchmarkResult, render_markdown, run_benchmark

GOLDEN = pathlib.Path("tests/fixtures/golden")


@pytest.fixture
def predictions(tmp_path: pathlib.Path) -> pathlib.Path:
    """Give each test a writable copy of the golden fixtures to damage."""
    target = tmp_path / "predicted"
    shutil.copytree(GOLDEN, target)
    return target


def edit(directory: pathlib.Path, name: str, mutate: Callable[[Any], Any]) -> None:
    """Load a fixture, apply a mutation, and write it back."""
    path = directory / name
    payload = json.loads(path.read_text())
    path.write_text(json.dumps(mutate(payload), indent=2))


def test_self_comparison_is_perfect() -> None:
    """Assert the harness scores the fixtures against themselves without error."""
    result = run_benchmark(GOLDEN, GOLDEN)
    assert result.metrics["detection_recall"] == 1.0
    assert result.metrics["unsupported_claim_rate"] == 0.0
    assert result.failures == []


def test_self_comparison_records_that_it_proves_nothing() -> None:
    """Assert the report warns that a self-comparison says nothing about a model."""
    result = run_benchmark(GOLDEN, GOLDEN)
    assert any("prove the harness works" in note for note in result.notes)


def test_dropping_detections_lowers_recall(predictions: pathlib.Path) -> None:
    """Assert removing observations is caught as a recall failure."""
    edit(predictions, "10_observations.json", lambda rows: rows[:4])
    result = run_benchmark(predictions, GOLDEN)
    assert result.metrics["detection_recall"] < 0.5
    assert "detection_recall" in result.failures


def test_shifting_a_box_lowers_precision(predictions: pathlib.Path) -> None:
    """Assert a badly-placed box stops counting as a hit."""

    def shift(rows: list[dict]) -> list[dict]:
        for row in rows:
            row["bbox"] = {"x1": 900.0, "y1": 900.0, "x2": 950.0, "y2": 950.0}
        return rows

    edit(predictions, "10_observations.json", shift)
    result = run_benchmark(predictions, GOLDEN)
    assert result.metrics["detection_precision"] == 0.0


def test_mistimed_events_lower_the_event_score(predictions: pathlib.Path) -> None:
    """Assert events reported five seconds late no longer match."""

    def delay(rows: list[dict]) -> list[dict]:
        for row in rows:
            row["timestamp_s"] = float(row["timestamp_s"]) + 5.0
        return rows

    edit(predictions, "40_events.json", delay)
    result = run_benchmark(predictions, GOLDEN)
    assert result.metrics["event_f1"] == 0.0
    assert "event_f1" in result.failures


def test_inventing_a_cross_camera_link_is_caught(predictions: pathlib.Path) -> None:
    """Assert a fabricated identity link raises the false-link rate.

    This is the failure that matters most: a false link invents a trajectory, and
    every conclusion downstream inherits it.
    """

    def fabricate(rows: list[dict]) -> list[dict]:
        rows.append(
            {
                "schema_version": "1.0.0",
                "link_id": "LNK-BAD",
                "run_id": "RUN-GOLD-001",
                "segment_a": "SEG-A-P01",
                "segment_b": "SEG-B-R12",
                "decision": "linked",
                "score": 0.99,
                "threshold": 0.75,
                "components": {},
                "evidence_refs": [],
            }
        )
        return rows

    edit(predictions, "30_identity_links.json", fabricate)
    result = run_benchmark(predictions, GOLDEN)
    assert result.metrics["false_link_rate"] > 0.05
    assert "false_link_rate" in result.failures


def test_a_dangling_citation_is_caught(predictions: pathlib.Path) -> None:
    """Assert a claim citing evidence that does not exist fails the run.

    A report can look fully covered while citing nothing real. This is the check
    that separates coverage from support.
    """

    def dangle(report: dict) -> dict:
        report["claims"][0]["evidence_refs"] = ["EVT-9999"]
        return report

    edit(predictions, "80_report.json", dangle)
    result = run_benchmark(predictions, GOLDEN)
    assert result.metrics["unsupported_claim_rate"] > 0.0
    assert "unsupported_claim_rate" in result.failures


def test_ranking_the_wrong_cause_first_is_caught(predictions: pathlib.Path) -> None:
    """Assert reversing the hypothesis ranking drops top-1 accuracy."""

    def reverse(report: dict) -> dict:
        report["ranked_hypotheses"] = list(reversed(report["ranked_hypotheses"]))
        return report

    edit(predictions, "80_report.json", reverse)
    result = run_benchmark(predictions, GOLDEN)
    assert result.metrics["cause_top_1"] == 0.0
    assert result.metrics["cause_top_3"] == 1.0


def test_report_renders_thresholds_and_a_verdict() -> None:
    """Assert the markdown report carries every metric and a clear verdict."""
    markdown = render_markdown(run_benchmark(GOLDEN, GOLDEN))
    assert "| Metric | Value | Threshold | Verdict |" in markdown
    assert "unsupported_claim_rate" in markdown
    assert "All thresholded metrics pass." in markdown


def test_failures_are_listed_in_the_report(predictions: pathlib.Path) -> None:
    """Assert a failing run names the metrics that failed."""
    edit(predictions, "10_observations.json", lambda rows: rows[:1])
    markdown = render_markdown(run_benchmark(predictions, GOLDEN))
    assert "below threshold" in markdown
    assert "detection_recall" in markdown


def test_inverted_metrics_use_a_ceiling_not_a_floor() -> None:
    """Assert lower-is-better metrics are judged against an upper bound."""
    result = BenchmarkResult(
        dataset_version="x",
        run_id="y",
        device="z",
        generated_at=run_benchmark(GOLDEN, GOLDEN).generated_at,
    )
    result.metrics["false_link_rate"] = 0.01
    assert result.verdict("false_link_rate") == "PASS"
    result.metrics["false_link_rate"] = 0.20
    assert result.verdict("false_link_rate") == "FAIL"
