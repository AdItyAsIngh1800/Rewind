"""Video ingestion: probe metadata and sample frames deterministically.

The first stage of the pipeline. Its job is narrow on purpose: turn a video file into
metadata and a reproducible sequence of frames, and put every frame on the shared
timebase. It knows nothing about detection.

DETERMINISM IS THE POINT. The same input must always yield the same frames, because a
processing run that cannot be replayed cannot be audited, and a benchmark that shifts
because sampling drifted is not a benchmark. This was originally justified by GPU
budget; measurement showed the machine has roughly ten times the throughput the
dataset needs, so the reason is now reproducibility alone. That reason is unaffected
by having a fast machine.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

#: A decoded frame: height x width x 3, BGR, as OpenCV returns it.
Frame = NDArray[np.uint8]


class IngestionError(RuntimeError):
    """Raised when a video cannot be read or its metadata is unusable."""


@dataclass(frozen=True)
class VideoMetadata:
    """What a video file declares about itself.

    Read with ``ffprobe`` rather than by decoding: the container header is
    authoritative for frame rate and duration, and decoding an entire clip only to
    count frames is wasteful when the answer is in the first few kilobytes.
    """

    path: pathlib.Path
    width: int
    height: int
    fps: float
    frame_count: int
    duration_s: float
    codec: str

    @property
    def sha256(self) -> str:
        """Content hash of the file, used as part of a run's input hash."""
        return hash_file(self.path)


@dataclass(frozen=True)
class SampledFrame:
    """One frame selected for processing, placed on the shared timebase."""

    camera_id: str
    source_index: int
    sampled_index: int
    #: Seconds from the start of this clip, before any clock correction.
    source_time_s: float
    #: Seconds on the shared timebase, after the camera's clock offset is applied.
    timestamp_s: float


def hash_file(path: pathlib.Path, chunk: int = 1 << 20) -> str:
    """Hash a file's contents, streaming so a large video never lands in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def _parse_rate(value: str) -> float:
    """Parse an ffprobe rational such as ``30000/1001`` into a float.

    ffprobe reports frame rate as an exact rational. Rounding it here would put
    NTSC-style rates a frame out of step over a 45 second clip, which is enough to
    misorder events between cameras.
    """
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        denom = float(denominator)
        if denom == 0:
            raise IngestionError(f"invalid frame rate {value!r}")
        return float(numerator) / denom
    return float(value)


def case_clips(case_dir: pathlib.Path) -> list[pathlib.Path]:
    """Return the camera clips in a case directory, in camera order, skipping hidden files.

    A clip's stem is its camera id, so every stray ``*.mp4`` becomes a camera. macOS
    writes ``._CAM_A.mp4`` AppleDouble files beside the real ones when a directory is
    archived or copied to another filesystem; the first published data asset carried
    56 of them, and the worker failed reading one as a video (E10.1, Gate 6).
    """
    return sorted(p for p in case_dir.glob("*.mp4") if not p.name.startswith("."))


def probe(path: pathlib.Path) -> VideoMetadata:
    """Read a video's metadata without decoding it."""
    if not path.exists():
        raise IngestionError(f"no such video: {path}")

    try:
        output = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,avg_frame_rate,nb_frames,codec_name:format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except FileNotFoundError as exc:
        raise IngestionError("ffprobe is not installed; run `brew install ffmpeg`") from exc
    except subprocess.CalledProcessError as exc:
        raise IngestionError(f"ffprobe failed on {path}: {exc.stderr.strip()}") from exc

    payload = json.loads(output)
    streams = payload.get("streams") or []
    if not streams:
        raise IngestionError(f"{path} contains no video stream")
    stream = streams[0]

    fps = _parse_rate(stream.get("avg_frame_rate", "0/1"))
    if fps <= 0:
        raise IngestionError(f"{path} reports a non-positive frame rate")

    duration = float(payload.get("format", {}).get("duration", 0.0))
    declared = stream.get("nb_frames")
    # Some encoders omit nb_frames. Deriving it from duration is close enough for
    # sampling, and the exact count is recomputed while decoding anyway.
    frame_count = int(declared) if declared not in (None, "N/A") else round(duration * fps)

    return VideoMetadata(
        path=path,
        width=int(stream["width"]),
        height=int(stream["height"]),
        fps=fps,
        frame_count=frame_count,
        duration_s=duration,
        codec=str(stream.get("codec_name", "unknown")),
    )


def sample_indices(source_fps: float, frame_count: int, target_fps: float) -> list[int]:
    """Choose which source frames to process.

    Selection is a pure function of the three arguments, so it can be recomputed
    later to prove which frames a past run saw. Frames are chosen by rounding an
    evenly spaced time grid rather than by a fixed stride: a stride drifts when the
    ratio is not an integer, and a 29.97 to 10 FPS conversion would slowly slide out
    of step with the other cameras.
    """
    if source_fps <= 0:
        raise IngestionError("source frame rate must be positive")
    if target_fps <= 0:
        raise IngestionError("target frame rate must be positive")
    if frame_count <= 0:
        return []

    if target_fps >= source_fps:
        # Never invent frames. Asking for more than the source has yields all of it.
        return list(range(frame_count))

    duration = frame_count / source_fps
    wanted = int(duration * target_fps)
    indices = []
    seen: set[int] = set()
    for step in range(wanted):
        index = min(frame_count - 1, round(step / target_fps * source_fps))
        if index not in seen:
            seen.add(index)
            indices.append(index)
    return indices


def shared_timebase(source_time_s: float, clock_offset_s: float) -> float:
    """Convert a clip-local time to the shared timebase.

    The offset is *subtracted*: a camera whose clock runs 0.4 s fast timestamps an
    event 0.4 s later than it happened, so the correction pulls it back. Getting this
    backwards doubles the error instead of removing it, which is why the direction is
    asserted in the tests rather than left to a reader.
    """
    return source_time_s - clock_offset_s


def plan_sampling(
    metadata: VideoMetadata, camera_id: str, target_fps: float, clock_offset_s: float = 0.0
) -> list[SampledFrame]:
    """Produce the full sampling plan for one camera without decoding anything.

    Separating the plan from the decode means a run can record exactly which frames
    it intended to process, and a later replay can verify it processed them.
    """
    frames: list[SampledFrame] = []
    for position, source_index in enumerate(
        sample_indices(metadata.fps, metadata.frame_count, target_fps)
    ):
        source_time = source_index / metadata.fps
        frames.append(
            SampledFrame(
                camera_id=camera_id,
                source_index=source_index,
                sampled_index=position,
                source_time_s=source_time,
                timestamp_s=shared_timebase(source_time, clock_offset_s),
            )
        )
    return frames


def decode_frames(path: pathlib.Path, indices: list[int]) -> Iterator[tuple[int, Frame]]:
    """Yield ``(source_index, frame)`` for the requested indices.

    Decodes sequentially and keeps the frames it was asked for, rather than seeking.
    Seeking by frame number is unreliable on inter-frame codecs: a seek lands on the
    nearest keyframe and silently returns a different frame, which would break the
    determinism this module exists to provide.
    """
    try:
        import cv2
    except ImportError as exc:
        raise IngestionError("opencv is required to decode frames; run `make dev`") from exc

    wanted = set(indices)
    if not wanted:
        return

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise IngestionError(f"could not open {path}")
    try:
        index = 0
        remaining = len(wanted)
        while remaining > 0:
            ok, frame = capture.read()
            if not ok:
                break
            if index in wanted:
                remaining -= 1
                # OpenCV's stub types the frame as a union of Mat and a generic
                # ndarray. For a decoded BGR video frame it is always uint8 HxWx3,
                # and narrowing here keeps every downstream consumer honestly typed.
                yield index, np.asarray(frame, dtype=np.uint8)
            index += 1
    finally:
        capture.release()


def input_hash(paths: list[pathlib.Path]) -> str:
    """Hash an ordered set of inputs into one identifier for a processing run.

    Names are included alongside contents so that reordering or renaming cameras
    produces a different run, which it should: CAM_A and CAM_B swapped is a different
    experiment, not the same one.
    """
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(hash_file(path).encode())
    return f"sha256:{digest.hexdigest()}"
