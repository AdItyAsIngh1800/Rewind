"""ADR-0006 moved the run contract additively: a 1.0.0 run still parses."""

from __future__ import annotations

from packages.schemas import ProcessingRun


def test_a_run_written_before_the_media_fields_still_validates() -> None:
    """Assert the new fields are optional, so a 1.0.0 document needs no migration to parse."""
    run = ProcessingRun.model_validate(
        {
            "schema_version": "1.0.0",
            "run_id": "r",
            "input_hash": "h",
            "dataset_version": "v1",
            "config_version": "c",
        }
    )
    assert run.media_uris == {} and run.captured_at is None
