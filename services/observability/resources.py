"""How much memory this process has held, for the run record (ADR-0008, spec §N).

The worker handles one run at a time, so the process's peak at the end of a run is
that run's peak. Accelerator memory is counted only when torch is already loaded: the
API and the tests never import it, and importing a deep-learning framework to report
that it holds no memory would cost more than the measurement is worth.
"""

from __future__ import annotations

import resource
import sys


def peak_resident_mb() -> float:
    """Peak resident set size of this process so far, in megabytes.

    ``ru_maxrss`` is bytes on macOS and kilobytes on Linux; the container runs Linux and
    development runs macOS, so the unit is not assumed.
    """
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 1e6 if sys.platform == "darwin" else peak / 1e3


def accelerator_mb() -> float:
    """Memory the accelerator driver holds for this process, in megabytes; 0 without one."""
    torch = sys.modules.get("torch")
    if torch is None:
        return 0.0
    if torch.backends.mps.is_available():
        return float(torch.mps.driver_allocated_memory()) / 1e6
    if torch.cuda.is_available():
        return float(torch.cuda.max_memory_allocated()) / 1e6
    return 0.0


def peak_memory_mb() -> float:
    """Resident plus accelerator memory, rounded to a tenth of a megabyte."""
    return round(peak_resident_mb() + accelerator_mb(), 1)
