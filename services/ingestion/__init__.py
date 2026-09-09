"""Video ingestion.

Metadata extraction, deterministic frame sampling and timestamp normalization onto
the shared timebase.
"""

from .video import (
    IngestionError,
    SampledFrame,
    VideoMetadata,
    decode_frames,
    hash_file,
    input_hash,
    plan_sampling,
    probe,
    sample_indices,
    shared_timebase,
)

__all__ = [
    "IngestionError",
    "SampledFrame",
    "VideoMetadata",
    "decode_frames",
    "hash_file",
    "input_hash",
    "plan_sampling",
    "probe",
    "sample_indices",
    "shared_timebase",
]
