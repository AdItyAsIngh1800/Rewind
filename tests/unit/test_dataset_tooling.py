"""Tests for the dataset tooling: ground-truth validation and the manifest.

These run without Blender. The validator is fed hand-built exports that are wrong in
specific, known ways, because a validator that has only ever seen valid input is an
assumption rather than a check.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from _pytest.monkeypatch import MonkeyPatch

from packages.schemas import SCHEMA_VERSION
from scripts.dataset.make_manifest import SPLITS, describe_case, sha256
from scripts.dataset.validate_ground_truth import (
    GroundTruthError,
    check_coverage,
    validate_case,
    validate_events,
    validate_observations,
)


def observation(**overrides: object) -> dict:
    """Build a valid ground-truth observation, overridable per test."""
    row = {
        "observation_id": "GT-0001",
        "run_id": "GT",
        "camera_id": "CAM_A",
        "frame_index": 128,
        "timestamp_s": 12.8,
        "entity_class": "person",
        "bbox": {"x1": 100.0, "y1": 200.0, "x2": 160.0, "y2": 380.0},
        "confidence": 1.0,
        "entity_id": "P01",
        "world_xyz": [12.0, 9.5, 0.0],
        "visibility": 1.0,
    }
    row.update(overrides)
    return row


# --------------------------------------------------------------------------
# Observation validation
# --------------------------------------------------------------------------


def test_a_clean_export_produces_no_problems() -> None:
    """Assert valid ground truth passes without complaint."""
    assert validate_observations([observation()]) == []


def test_schema_version_is_supplied_for_blender() -> None:
    """Assert the validator fills in the version Blender cannot know.

    Blender runs its own bundled Python with no access to packages.schemas, so the
    render script cannot stamp the contract version. Requiring it there would push a
    project constant into a file nobody would remember to update.
    """
    row = observation()
    validate_observations([row])
    assert row["schema_version"] == SCHEMA_VERSION


def test_a_degenerate_box_is_reported_with_its_row() -> None:
    """Assert a malformed bbox names the row rather than failing anonymously."""
    problems = validate_observations(
        [observation(bbox={"x1": 10.0, "y1": 10.0, "x2": 10.0, "y2": 20.0})]
    )
    assert problems and "row 0" in problems[0]


def test_every_bad_row_is_reported_not_just_the_first() -> None:
    """Assert the validator surveys the whole export.

    A renderer bug usually affects a class of frames, so seeing one example of each
    problem is more useful than stopping at the first.
    """
    problems = validate_observations([observation(confidence=5.0), observation(timestamp_s="soon")])
    assert len(problems) == 2


def test_an_almost_invisible_entity_should_not_have_been_emitted() -> None:
    """Assert ground truth never claims to see what a camera cannot.

    If it did, an occlusion case would score as a detector failure rather than as
    the evidence gap the whole product is built to report.
    """
    problems = validate_observations([observation(visibility=0.05)])
    assert problems and "should not have been emitted" in problems[0]


def test_a_racked_pallet_is_flagged_as_scenery() -> None:
    """Assert a pallet up in racking is caught.

    Stored goods are scenery, not entities. The scene is authored to hide racked
    pallets; this filter is the safety net, and the message says so.
    """
    problems = validate_observations(
        [observation(entity_class="pallet", entity_id="PL3", world_xyz=[12.0, 8.0, 2.4])]
    )
    assert problems and "racked" in problems[0]


def test_a_floor_level_pallet_is_accepted() -> None:
    """Assert the pallet that actually matters is not flagged."""
    rows = [observation(entity_class="pallet", entity_id="PL3", world_xyz=[12.0, 8.0, 0.08])]
    assert validate_observations(rows) == []


# --------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------


def test_a_single_camera_export_is_rejected() -> None:
    """Assert a partial render is caught.

    An export that silently rendered one camera looks fine row by row and is
    worthless as ground truth for a cross-camera system.
    """
    problems = check_coverage([observation(camera_id="CAM_A")])
    assert problems and "only 1 camera" in problems[0]


def test_all_three_cameras_satisfy_coverage() -> None:
    """Assert a complete render passes the coverage check."""
    rows = [observation(camera_id=c) for c in ("CAM_A", "CAM_B", "CAM_C")]
    assert check_coverage(rows) == []


def test_an_empty_export_is_rejected() -> None:
    """Assert an export with no observations is reported rather than passing."""
    problems = check_coverage([])
    assert any("no observations" in p for p in problems)


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------


def test_a_zone_event_without_a_zone_is_rejected() -> None:
    """Assert the contract's own invariant is enforced on annotated events."""
    problems = validate_events(
        [
            {
                "event_id": "E1",
                "run_id": "GT",
                "event_type": "zone_entry",
                "timestamp_s": 12.8,
                "confidence": 1.0,
            }
        ]
    )
    assert problems and "zone_id" in problems[0]


# --------------------------------------------------------------------------
# Case directories
# --------------------------------------------------------------------------


def test_a_missing_export_names_the_file(tmp_path: pathlib.Path) -> None:
    """Assert a missing observations file fails with the path, not a traceback."""
    with pytest.raises(GroundTruthError, match="missing export"):
        validate_case(tmp_path)


def test_missing_annotation_files_are_each_reported(tmp_path: pathlib.Path) -> None:
    """Assert every required annotation file is checked for.

    gaps_gt.json in particular is the ground truth for the uncertainty engine.
    Without it the occlusion case cannot be scored at all.
    """
    (tmp_path / "observations_gt.json").write_text(
        json.dumps([observation(camera_id=c) for c in ("CAM_A", "CAM_B", "CAM_C")])
    )
    problems = validate_case(tmp_path)
    for required in ("events_gt.json", "identities_gt.json", "cause_gt.json", "gaps_gt.json"):
        assert any(required in p for p in problems)


# --------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------


def test_hash_is_stable_and_content_sensitive(tmp_path: pathlib.Path) -> None:
    """Assert the checksum changes when the bytes change and not otherwise."""
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"frame-data")
    first = sha256(path)
    assert first == sha256(path)
    path.write_bytes(b"frame-data-edited")
    assert sha256(path) != first


def test_a_case_directory_is_described_with_hashes(
    tmp_path: pathlib.Path, monkeypatch: MonkeyPatch
) -> None:
    """Assert every file in a case is recorded with its size and hash."""
    import scripts.dataset.make_manifest as manifest_module

    case = tmp_path / "case_01"
    case.mkdir()
    (case / "CAM_A.mp4").write_bytes(b"aaa")
    (case / "observations_gt.json").write_text("[]")
    monkeypatch.setattr(manifest_module, "SAMPLES", tmp_path)

    described = describe_case(case)
    assert described["case"] == "case_01"
    assert described["split"] == "tune"
    assert described["file_count"] == 2
    assert all(len(f["sha256"]) == 64 for f in described["files"])


def test_golden_cases_are_held_out() -> None:
    """Assert exactly two cases are golden and they are the occlusion pair.

    case_02 is the occlusion case and case_06 is the ambiguous-cause case. Those are
    the two that actually test the product's claim, which is why they are the two
    withheld until Week 17.
    """
    golden = {case for case, split in SPLITS.items() if split == "golden"}
    assert golden == {"case_02", "case_06"}
    assert sum(1 for s in SPLITS.values() if s == "tune") == 4
