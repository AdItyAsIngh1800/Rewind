"""Tests for perception persistence.

The property under test is that the write path is safe to retry and the read path
meets the 500 ms budget on real data volumes. Database fixtures live in
``conftest.py``.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from sqlalchemy.orm import Session

from packages.database.models import Camera, ProcessingRun
from packages.schemas import EntityClass, Observation, TrackSegment
from services.perception import (
    observations_in_window,
    segments_for_run,
    timed_window_query,
    write_observations,
    write_segments,
)
from tests.integration.conftest import needs_db

CASE = pathlib.Path("data/samples/case_01/observations_gt.json")
RUN_ID = "run-persist-test"

#: The non-functional target from the specification: ordinary metadata queries
#: return in under 500 ms locally.
WINDOW_BUDGET_MS = 500.0


@pytest.fixture
def run(session: Session) -> ProcessingRun:
    """Create a processing run and its cameras so foreign keys resolve."""
    for camera_id in ("CAM_A", "CAM_B", "CAM_C"):
        session.add(
            Camera(
                camera_id=camera_id,
                name=camera_id,
                source_uri="file:///x",
                width=1280,
                height=720,
                fps=10.0,
            )
        )
    processing_run = ProcessingRun(
        run_id=RUN_ID,
        input_hash="sha256:test",
        dataset_version="v1",
        config_version="test",
        status="running",
    )
    session.add(processing_run)
    session.flush()
    return processing_run


@pytest.fixture
def ground_truth() -> list[Observation]:
    """All of case_01's ray-cast observations, re-stamped with the test run id."""
    if not CASE.exists():
        pytest.skip("case_01 ground truth has not been generated")
    rows = json.loads(CASE.read_text())
    return [Observation.model_validate({**row, "run_id": RUN_ID}) for row in rows]


@needs_db
def test_all_observations_are_written(
    session: Session, run: ProcessingRun, ground_truth: list[Observation]
) -> None:
    """Assert a full case writes every row."""
    inserted = write_observations(session, ground_truth)
    assert inserted == len(ground_truth)


@needs_db
def test_rewriting_is_idempotent(
    session: Session, run: ProcessingRun, ground_truth: list[Observation]
) -> None:
    """Assert a retried write inserts nothing and raises nothing.

    A worker that dies after persisting and is redelivered must be able to run the
    whole stage again without duplicating rows or failing on the ones present.
    """
    write_observations(session, ground_truth)
    inserted_again = write_observations(session, ground_truth)
    assert inserted_again == 0


@needs_db
def test_window_query_returns_the_right_rows(
    session: Session, run: ProcessingRun, ground_truth: list[Observation]
) -> None:
    """Assert the window query is exact on its bounds and camera."""
    write_observations(session, ground_truth)
    rows = observations_in_window(session, RUN_ID, "CAM_B", 13.0, 14.0)
    expected = [o for o in ground_truth if o.camera_id == "CAM_B" and 13.0 <= o.timestamp_s <= 14.0]
    assert len(rows) == len(expected)
    assert all(r.camera_id == "CAM_B" for r in rows)
    assert [r.timestamp_s for r in rows] == sorted(r.timestamp_s for r in rows)


@needs_db
def test_window_query_meets_the_latency_budget(
    session: Session, run: ProcessingRun, ground_truth: list[Observation]
) -> None:
    """Assert a one-second window on a full case returns inside 500 ms.

    Measured, not assumed. This is a local Postgres so it says nothing about the
    Supabase pooler; ``timed_window_query`` exists so the same measurement can be
    taken there.
    """
    write_observations(session, ground_truth)
    _rows, elapsed_ms = timed_window_query(session, RUN_ID, "CAM_A", 12.0, 13.0)
    assert elapsed_ms < WINDOW_BUDGET_MS, f"window query took {elapsed_ms:.0f} ms"


@needs_db
def test_segments_round_trip(session: Session, run: ProcessingRun) -> None:
    """Assert a written segment reads back with its observation ids intact."""
    segment = TrackSegment(
        segment_id="SEG-test-1",
        run_id=RUN_ID,
        camera_id="CAM_A",
        local_track_id="CAM_A-T001",
        entity_class=EntityClass.PERSON,
        start_time_s=1.0,
        end_time_s=2.0,
        observation_ids=["a", "b", "c"],
        mean_confidence=0.9,
    )
    assert write_segments(session, [segment]) == 1
    assert write_segments(session, [segment]) == 0
    (row,) = segments_for_run(session, RUN_ID)
    assert row.observation_ids == ["a", "b", "c"]
    assert row.entity_class == "person"
