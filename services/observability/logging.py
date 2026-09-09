"""Console logging setup shared by every entry point.

Exists so that no module has to decide how a log line is formatted, and so that
nothing in this codebase reaches for ``print``. Modules take a
``logging.getLogger(__name__)`` and log to it; the process entry point calls
``configure_logging`` exactly once.

Stdlib logging rather than structlog, deliberately, even though structlog is the
locked choice in ROADMAP E10.2. Every module logs through a stdlib logger either
way — E10.2 swaps this function's formatter for structlog's ``ProcessorFormatter``
and gains JSON output without touching a single call site.
"""

from __future__ import annotations

import logging
import os
import sys

DEFAULT_LEVEL = "INFO"


def configure_logging(level: int | str | None = None) -> None:
    """Install a stdout handler that emits the bare message, replacing any existing one.

    Args:
        level: Threshold to install. Defaults to ``$REWIND_LOG_LEVEL``, then ``INFO``.

    Output goes to stdout with no timestamp or level prefix because these commands
    are read by a person at a terminal and several of them (the benchmark report,
    the accelerator table) are meant to be piped or pasted verbatim. Level and
    timestamp arrive in E10.2 along with the JSON renderer, where a log aggregator
    rather than a person is the reader. ``force`` is set so that a second entry
    point in the same process — a script importing the API app, for instance —
    still gets this configuration rather than silently keeping an earlier one.

    """
    logging.basicConfig(
        level=level if level is not None else os.environ.get("REWIND_LOG_LEVEL", DEFAULT_LEVEL),
        format="%(message)s",
        stream=sys.stdout,
        force=True,
    )
