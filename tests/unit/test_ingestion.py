"""Tests for video ingestion.

The two properties that matter here are determinism and clock direction. A run that
cannot be replayed frame for frame cannot be audited, and a clock correction applied
the wrong way round doubles the error it was meant to remove.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

from services.ingestion import (
    IngestionError,
    hash_file,
    input_hash,
    plan_sampling,
    probe,
    sample_indices,
    shared_timebase,
)
from services.ingestion.video import VideoMetadata

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg is not installed")


@pytest.fixture(scope="module")
def clip(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """Render a tiny synthetic clip so probing is tested against a real container."""
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg is not installed")
    path = tmp_path_factory.mktemp("video") / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=10:duration=3",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path


def meta(fps: float, frames: int) -> VideoMetadata:
    """Build metadata without touching a file, for pure sampling tests."""
    return VideoMetadata(
        path=pathlib.Path("synthetic.mp4"),
        width=1280,
        height=720,
        fps=fps,
        frame_count=frames,
        duration_s=frames / fps,
        codec="h264",
    )


# --------------------------------------------------------------------------
# Deterministic sampling
# --------------------------------------------------------------------------


def test_sampling_is_reproducible() -> None:
    """Assert the same arguments always select the same frames.

    This is the whole justification for deterministic sampling. Originally it was
    about GPU budget; measurement showed ten times the needed throughput, so
    reproducibility is now the only reason, and it is a sufficient one.
    """
    first = sample_indices(30.0, 900, 10.0)
    second = sample_indices(30.0, 900, 10.0)
    assert first == second


def test_integer_ratio_takes_every_nth_frame() -> None:
    """Assert 30 to 10 FPS keeps every third frame."""
    assert sample_indices(30.0, 30, 10.0)[:5] == [0, 3, 6, 9, 12]


def test_matching_rates_keep_every_frame() -> None:
    """Assert a 10 FPS source sampled at 10 FPS is untouched.

    This is the project's own dataset, so the common path must not resample.
    """
    assert sample_indices(10.0, 450, 10.0) == list(range(450))


def test_sampling_never_invents_frames() -> None:
    """Assert asking for more than the source has yields only what exists.

    Upsampling would fabricate observations, and a fabricated frame is a fabricated
    piece of evidence.
    """
    assert sample_indices(10.0, 20, 30.0) == list(range(20))


def test_non_integer_ratio_does_not_drift() -> None:
    """Assert a 29.97 to 10 FPS conversion stays in step across a long clip.

    A fixed stride drifts when the ratio is not an integer. Over 45 seconds that
    accumulates to more than a frame, which is enough to misorder events between
    cameras that are supposed to share a clock.
    """
    fps = 30000 / 1001
    frames = int(fps * 45)
    indices = sample_indices(fps, frames, 10.0)
    # Every selected frame should sit within half a frame of its ideal time.
    for position, index in enumerate(indices):
        ideal = position / 10.0
        actual = index / fps
        assert abs(actual - ideal) <= 0.5 / fps


def test_empty_video_samples_nothing() -> None:
    """Assert a zero-length video yields no frames rather than raising."""
    assert sample_indices(30.0, 0, 10.0) == []


@pytest.mark.parametrize(("source", "target"), [(0.0, 10.0), (30.0, 0.0), (-1.0, 10.0)])
def test_non_positive_rates_are_rejected(source: float, target: float) -> None:
    """Assert a nonsensical frame rate fails loudly rather than dividing by zero."""
    with pytest.raises(IngestionError):
        sample_indices(source, 100, target)


# --------------------------------------------------------------------------
# The shared timebase
# --------------------------------------------------------------------------


def test_a_fast_clock_is_pulled_back() -> None:
    """Assert a positive offset is subtracted, not added.

    CAM_B's clock runs 0.4 s fast, so it stamps an event 0.4 s later than it
    happened. The correction must pull it back to 12.4 s. Adding instead would move
    it to 13.2 s and double the error the correction exists to remove.
    """
    assert shared_timebase(12.8, clock_offset_s=0.4) == pytest.approx(12.4)


def test_a_slow_clock_is_pushed_forward() -> None:
    """Assert a negative offset moves the timestamp later.

    CAM_C's clock runs 0.2 s slow, so its 12.8 s is really 13.0 s.
    """
    assert shared_timebase(12.8, clock_offset_s=-0.2) == pytest.approx(13.0)


def test_the_reference_camera_is_unchanged() -> None:
    """Assert a zero offset is a no-op."""
    assert shared_timebase(12.8, clock_offset_s=0.0) == 12.8


def test_offsets_bring_three_cameras_into_agreement() -> None:
    """Assert the scene's real offsets align a simultaneous event.

    One event seen by all three cameras is stamped differently by each. After
    correction all three must agree, or cross-camera ordering is meaningless.
    """
    true_time = 13.4
    stamped = {"CAM_A": true_time + 0.0, "CAM_B": true_time + 0.4, "CAM_C": true_time - 0.2}
    offsets = {"CAM_A": 0.0, "CAM_B": 0.4, "CAM_C": -0.2}
    corrected = {c: shared_timebase(stamped[c], offsets[c]) for c in stamped}
    assert all(value == pytest.approx(true_time) for value in corrected.values())


# --------------------------------------------------------------------------
# Sampling plans
# --------------------------------------------------------------------------


def test_a_plan_places_every_frame_on_the_shared_timebase() -> None:
    """Assert planned frames carry both source and corrected times."""
    plan = plan_sampling(meta(10.0, 30), camera_id="CAM_B", target_fps=10.0, clock_offset_s=0.4)
    assert len(plan) == 30
    assert plan[0].source_time_s == 0.0
    assert plan[0].timestamp_s == pytest.approx(-0.4)
    assert plan[10].source_time_s == pytest.approx(1.0)
    assert plan[10].timestamp_s == pytest.approx(0.6)


def test_plan_indices_are_contiguous_even_when_frames_are_skipped() -> None:
    """Assert sampled_index counts selections while source_index tracks the file."""
    plan = plan_sampling(meta(30.0, 90), camera_id="CAM_A", target_fps=10.0)
    assert [f.sampled_index for f in plan] == list(range(len(plan)))
    assert plan[1].source_index == 3


# --------------------------------------------------------------------------
# Hashing and run identity
# --------------------------------------------------------------------------


def test_hash_changes_with_content(tmp_path: pathlib.Path) -> None:
    """Assert the file hash is content sensitive."""
    path = tmp_path / "a.mp4"
    path.write_bytes(b"one")
    first = hash_file(path)
    path.write_bytes(b"two")
    assert hash_file(path) != first


def test_input_hash_is_order_independent(tmp_path: pathlib.Path) -> None:
    """Assert the run identity does not depend on argument order.

    The same three clips passed in any order are the same run.
    """
    paths = []
    for name in ("CAM_A.mp4", "CAM_B.mp4", "CAM_C.mp4"):
        path = tmp_path / name
        path.write_bytes(name.encode())
        paths.append(path)
    assert input_hash(paths) == input_hash(list(reversed(paths)))


def test_renaming_a_camera_changes_the_run(tmp_path: pathlib.Path) -> None:
    """Assert swapping camera names produces a different run.

    CAM_A and CAM_B exchanged is a different experiment, not the same one, because
    every downstream geometric assumption is keyed to which camera is which.
    """
    first = tmp_path / "CAM_A.mp4"
    first.write_bytes(b"same-content")
    before = input_hash([first])
    renamed = tmp_path / "CAM_B.mp4"
    first.rename(renamed)
    assert input_hash([renamed]) != before


# --------------------------------------------------------------------------
# Probing a real file
# --------------------------------------------------------------------------


@needs_ffmpeg
def test_probe_reads_real_metadata(clip: pathlib.Path) -> None:
    """Assert probing a real container returns usable metadata."""
    metadata = probe(clip)
    assert (metadata.width, metadata.height) == (320, 240)
    assert metadata.fps == pytest.approx(10.0)
    assert metadata.duration_s == pytest.approx(3.0, abs=0.2)
    assert metadata.frame_count >= 29


@needs_ffmpeg
def test_probe_does_not_decode(clip: pathlib.Path) -> None:
    """Assert metadata is cheap enough to call on every file in a run."""
    metadata = probe(clip)
    assert metadata.codec == "h264"
    assert len(metadata.sha256) == 64


def test_probing_a_missing_file_names_it(tmp_path: pathlib.Path) -> None:
    """Assert a missing video fails with its path, not a traceback."""
    with pytest.raises(IngestionError, match="no such video"):
        probe(tmp_path / "absent.mp4")


@needs_ffmpeg
def test_probing_a_non_video_is_rejected(tmp_path: pathlib.Path) -> None:
    """Assert a text file masquerading as a video is caught."""
    fake = tmp_path / "not-a-video.mp4"
    fake.write_text("this is not a video")
    with pytest.raises(IngestionError):
        probe(fake)
