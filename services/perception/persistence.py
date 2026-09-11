"""Persist and query perception output.

Everything downstream of perception reads from here rather than from video. Once a
run has been processed, the evidence graph, the incident detector and the timeline
never touch a frame again; they query observations and segments by run, camera and
time. That is what makes reprocessing a case with a new model cheap, and what makes
a report auditable: the rows it cites are the rows that were written, unchanged.

Writes are bulk and idempotent on primary key. A retried job that re-persists the
same observations must not duplicate them and must not fail on the ones already
present, which is what ``ON CONFLICT DO NOTHING`` gives without a read-before-write.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from packages.database.models import Observation as ObservationRow
from packages.database.models import TrackSegment as TrackSegmentRow
from packages.schemas import Observation, TrackSegment

log = logging.getLogger(__name__)

#: Rows per INSERT statement. Large enough that a 450-frame camera is a handful of
#: round trips over the pooler; small enough that a statement stays well under
#: Postgres' parameter limit with fourteen columns per row.
BATCH = 2000


def _observation_values(observation: Observation) -> dict[str, object]:
    """Flatten a contract into the column shape the table stores."""
    return {
        "observation_id": observation.observation_id,
        "run_id": observation.run_id,
        "camera_id": observation.camera_id,
        "frame_index": observation.frame_index,
        "timestamp_s": observation.timestamp_s,
        "entity_class": observation.entity_class.value,
        "x1": observation.bbox.x1,
        "y1": observation.bbox.y1,
        "x2": observation.bbox.x2,
        "y2": observation.bbox.y2,
        "confidence": observation.confidence,
        "track_id": observation.track_id,
        "entity_id": observation.entity_id,
        "world_xyz": (
            {
                "x": observation.world_xyz[0],
                "y": observation.world_xyz[1],
                "z": observation.world_xyz[2],
            }
            if observation.world_xyz
            else None
        ),
        "visibility": observation.visibility,
    }


def _segment_values(segment: TrackSegment) -> dict[str, object]:
    """Flatten a track segment contract into its row."""
    return {
        "segment_id": segment.segment_id,
        "run_id": segment.run_id,
        "camera_id": segment.camera_id,
        "local_track_id": segment.local_track_id,
        "entity_class": segment.entity_class.value,
        "start_time_s": segment.start_time_s,
        "end_time_s": segment.end_time_s,
        "observation_ids": list(segment.observation_ids),
        "mean_confidence": segment.mean_confidence,
    }


def write_observations(session: Session, observations: Sequence[Observation]) -> int:
    """Bulk-insert observations, skipping any already present.

    Returns the number of rows actually inserted, which a caller can compare against
    the number offered to detect a partial earlier write.
    """
    inserted = 0
    for start in range(0, len(observations), BATCH):
        chunk = [_observation_values(o) for o in observations[start : start + BATCH]]
        # RETURNING rather than rowcount: psycopg reports rowcount as -1 for a
        # multi-row INSERT ... ON CONFLICT, so it cannot say how many rows landed.
        # RETURNING yields exactly the rows that were inserted and none that were
        # skipped, which is the number a retry check needs.
        statement = (
            insert(ObservationRow)
            .values(chunk)
            .on_conflict_do_nothing(index_elements=["observation_id"])
            .returning(ObservationRow.observation_id)
        )
        inserted += len(session.execute(statement).all())
    session.flush()
    log.info("wrote %d of %d observations", inserted, len(observations))
    return inserted


def write_segments(session: Session, segments: Sequence[TrackSegment]) -> int:
    """Bulk-insert track segments, skipping any already present."""
    if not segments:
        return 0
    statement = (
        insert(TrackSegmentRow)
        .values([_segment_values(s) for s in segments])
        .on_conflict_do_nothing(index_elements=["segment_id"])
        .returning(TrackSegmentRow.segment_id)
    )
    affected = len(session.execute(statement).all())
    session.flush()
    log.info("wrote %d of %d segments", affected, len(segments))
    return affected


def observations_in_window(
    session: Session,
    run_id: str,
    camera_id: str,
    start_s: float,
    end_s: float,
) -> list[ObservationRow]:
    """Every observation from one camera within a time window, ordered by time.

    This is the access pattern every downstream stage uses, and the one the
    ``ix_obs_run_camera_time`` index exists for. The non-functional target is that it
    returns in under 500 ms locally; ``timed_window_query`` measures that.
    """
    statement = (
        select(ObservationRow)
        .where(
            ObservationRow.run_id == run_id,
            ObservationRow.camera_id == camera_id,
            ObservationRow.timestamp_s >= start_s,
            ObservationRow.timestamp_s <= end_s,
        )
        .order_by(ObservationRow.timestamp_s, ObservationRow.observation_id)
    )
    return list(session.scalars(statement))


def segments_for_run(session: Session, run_id: str) -> list[TrackSegmentRow]:
    """Every track segment a run produced, across all cameras."""
    statement = (
        select(TrackSegmentRow)
        .where(TrackSegmentRow.run_id == run_id)
        .order_by(TrackSegmentRow.camera_id, TrackSegmentRow.start_time_s)
    )
    return list(session.scalars(statement))


def timed_window_query(
    session: Session, run_id: str, camera_id: str, start_s: float, end_s: float
) -> tuple[list[ObservationRow], float]:
    """Run the window query and report wall time in milliseconds.

    Kept as a first-class function rather than a test helper so the number can be
    reported from a real run against Supabase, where the pooler and network are part
    of what the 500 ms budget has to cover.
    """
    started = time.perf_counter()
    rows = observations_in_window(session, run_id, camera_id, start_s, end_s)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return rows, elapsed_ms
