"""Video ingestion.

Metadata extraction, deterministic frame sampling and timestamp normalization onto
the shared timebase.
"""

from .registry import (
    RunConflictError,
    create_run,
    find_by_input,
    run_identity,
    transition,
)
from .video import (
    Frame,
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
    "Frame",
    "IngestionError",
    "RunConflictError",
    "SampledFrame",
    "VideoMetadata",
    "create_run",
    "decode_frames",
    "find_by_input",
    "hash_file",
    "input_hash",
    "plan_sampling",
    "probe",
    "run_identity",
    "sample_indices",
    "shared_timebase",
    "transition",
]
