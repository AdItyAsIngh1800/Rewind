"""Run the worker: ``python -m apps.worker`` (the container) or ``make worker``.

The process entry point, so it configures logging once, before the worker starts.
The ``arq`` command line installs its own plain-text logging and logs its first lines
before any worker hook runs, which would put unstructured lines into a JSON stream
(E10.2). ``--burst`` processes whatever is queued, then exits.
"""

from __future__ import annotations

import argparse

from arq.worker import run_worker

from apps.worker.main import WorkerSettings
from services.observability.logging import configure_logging


def main() -> int:
    """Configure logging, then run the ARQ worker until stopped (or the queue is empty)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--burst", action="store_true")
    args = parser.parse_args()
    configure_logging()
    run_worker(WorkerSettings, burst=args.burst)  # type: ignore[arg-type]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
