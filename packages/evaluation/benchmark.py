"""The benchmark harness: score a prediction set against ground truth.

Emits a dated markdown report into ``artifacts/benchmark-reports/``. Reports are
append-only — a previous report is never overwritten, because the point of keeping
them is being able to say which release changed which number.

Right now this scores the golden fixtures against themselves and returns 1.0
everywhere. That is the correct starting state: it proves the plumbing works before
any model exists, so that when the first real numbers arrive we already know the
harness is not the thing that is wrong.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

from packages.evaluation.metrics import (
    Counts,
    evidence_coverage,
    false_link_rate,
    match_detections,
    match_events,
    top_k_accuracy,
    unsupported_claim_rate,
)

#: Provisional floors from the project charter §6. These are replaced at Gate 1 with
#: values calibrated against the measured baseline. A floor may only be lowered with
#: an experiment record explaining why it was unreachable.
FLOORS: dict[str, float] = {
    "detection_recall": 0.90,
    "detection_precision": 0.85,
    "event_f1": 0.85,
    "evidence_coverage": 0.95,
}

#: Metrics where a *lower* number is better, so the floor is an upper bound.
INVERTED: frozenset[str] = frozenset({"false_link_rate", "unsupported_claim_rate"})

CEILINGS: dict[str, float] = {
    "false_link_rate": 0.05,
    "unsupported_claim_rate": 0.0,
}


@dataclass
class BenchmarkResult:
    """Every metric from one benchmark run, plus the context needed to reproduce it."""

    dataset_version: str
    run_id: str
    device: str
    generated_at: datetime
    metrics: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def verdict(self, name: str) -> str:
        """Return PASS, FAIL or a dash for one metric against its threshold."""
        value = self.metrics.get(name)
        if value is None:
            return "—"
        if name in INVERTED:
            return "PASS" if value <= CEILINGS[name] else "FAIL"
        if name in FLOORS:
            return "PASS" if value >= FLOORS[name] else "FAIL"
        return "—"

    @property
    def failures(self) -> list[str]:
        """Names of every metric currently below its threshold."""
        return [name for name in self.metrics if self.verdict(name) == "FAIL"]


def _load(directory: pathlib.Path, name: str) -> object:
    """Read one JSON artefact from a prediction or ground-truth directory."""
    return json.loads((directory / name).read_text())


def run_benchmark(predicted: pathlib.Path, truth: pathlib.Path) -> BenchmarkResult:
    """Score a prediction directory against a ground-truth directory.

    Both directories hold the same filenames — the golden fixture layout. Passing
    the same path for both is the self-check: it must return perfect scores, and if
    it does not, the harness is broken rather than the model.
    """
    run = _load(truth, "01_run.json")
    assert isinstance(run, dict)

    result = BenchmarkResult(
        dataset_version=str(run["dataset_version"]),
        run_id=str(run["run_id"]),
        device=str(run.get("device", "unknown")),
        generated_at=datetime.now(UTC),
    )

    # --- detection ---
    pred_obs = _load(predicted, "10_observations.json")
    true_obs = _load(truth, "10_observations.json")
    assert isinstance(pred_obs, list) and isinstance(true_obs, list)
    detection: Counts = match_detections(pred_obs, true_obs)
    result.metrics["detection_precision"] = detection.precision
    result.metrics["detection_recall"] = detection.recall
    result.metrics["detection_f1"] = detection.f1

    # --- events ---
    pred_events = _load(predicted, "40_events.json")
    true_events = _load(truth, "40_events.json")
    assert isinstance(pred_events, list) and isinstance(true_events, list)
    events, timing_errors = match_events(pred_events, true_events)
    result.metrics["event_precision"] = events.precision
    result.metrics["event_recall"] = events.recall
    result.metrics["event_f1"] = events.f1
    result.metrics["event_timing_error_s"] = (
        sum(abs(e) for e in timing_errors) / len(timing_errors) if timing_errors else 0.0
    )

    # --- cross-camera identity ---
    pred_links = _load(predicted, "30_identity_links.json")
    true_links = _load(truth, "30_identity_links.json")
    assert isinstance(pred_links, list) and isinstance(true_links, list)
    true_pairs = {
        frozenset({str(link["segment_a"]), str(link["segment_b"])})
        for link in true_links
        if link.get("decision") == "linked"
    }
    result.metrics["false_link_rate"] = false_link_rate(pred_links, true_pairs)

    # --- cause ranking ---
    pred_report = _load(predicted, "80_report.json")
    true_report = _load(truth, "80_report.json")
    assert isinstance(pred_report, dict) and isinstance(true_report, dict)
    true_ranked = list(true_report["ranked_hypotheses"])
    if true_ranked:
        result.metrics["cause_top_1"] = top_k_accuracy(
            list(pred_report["ranked_hypotheses"]), str(true_ranked[0]), k=1
        )
        result.metrics["cause_top_3"] = top_k_accuracy(
            list(pred_report["ranked_hypotheses"]), str(true_ranked[0]), k=3
        )

    # --- evidence quality: the thesis, measured ---
    claims = list(pred_report["claims"])
    graph = _load(predicted, "60_evidence_graph.json")
    assert isinstance(graph, dict)
    pred_hypotheses = _load(predicted, "70_hypotheses.json")
    assert isinstance(pred_hypotheses, list)
    known_ids = (
        {str(e["event_id"]) for e in pred_events}
        | {str(n["node_id"]) for n in graph["nodes"]}
        | {str(h["hypothesis_id"]) for h in pred_hypotheses}
    )
    result.metrics["evidence_coverage"] = evidence_coverage(claims)
    result.metrics["unsupported_claim_rate"] = unsupported_claim_rate(claims, known_ids)

    if predicted == truth:
        result.notes.append(
            "Predictions and ground truth are the same directory. Perfect scores here "
            "prove the harness works; they say nothing about any model."
        )
    return result


def render_markdown(result: BenchmarkResult) -> str:
    """Render a benchmark result as a markdown report."""
    stamp = result.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Benchmark — {result.generated_at.date()}",
        "",
        f"- **Generated:** {stamp}",
        f"- **Dataset version:** `{result.dataset_version}`",
        f"- **Run:** `{result.run_id}`",
        f"- **Device:** `{result.device}`",
        "",
    ]
    for note in result.notes:
        lines += [f"> {note}", ""]

    lines += ["| Metric | Value | Threshold | Verdict |", "|---|---|---|---|"]
    for name, value in result.metrics.items():
        if name in INVERTED:
            threshold = f"≤ {CEILINGS[name]:.2f}"
        elif name in FLOORS:
            threshold = f"≥ {FLOORS[name]:.2f}"
        else:
            threshold = "—"
        lines.append(f"| `{name}` | {value:.3f} | {threshold} | {result.verdict(name)} |")

    lines += ["", "## Verdict", ""]
    if result.failures:
        lines.append(f"**{len(result.failures)} metric(s) below threshold:**")
        lines += [f"- `{name}`" for name in result.failures]
    else:
        lines.append("All thresholded metrics pass.")
    lines += [
        "",
        "Thresholds are the provisional floors from the project charter §6. They are "
        "replaced at Gate 1 by values calibrated against the measured baseline.",
        "",
    ]
    return "\n".join(lines)
