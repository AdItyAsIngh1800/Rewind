"""Logging setup shared by every entry point.

Exists so that no module has to decide how a log line is formatted, and so that nothing
in this codebase reaches for ``print``. Modules take a ``logging.getLogger(__name__)``
and log to it; the process entry point calls ``configure_logging`` exactly once.

Two formats, one set of call sites. ``console`` prints the bare message, for a person at
a terminal: several commands (the benchmark report, the accelerator table) are meant
to be piped or pasted verbatim. ``json`` renders every record, the project's and every
library's, as one JSON object per line with timestamp, level and logger, for a log
aggregator (E10.2). The containers set ``REWIND_LOG_FORMAT=json``. Every call site is a
stdlib logger, so the switch is this module and nothing else.
"""

from __future__ import annotations

import logging
import os
import sys

import structlog

DEFAULT_LEVEL = "INFO"

#: Servers that install their own handlers, which would bypass the JSON formatter and
#: put plain-text lines into an otherwise structured stream.
_SELF_CONFIGURED = ("uvicorn", "uvicorn.error", "uvicorn.access", "arq")

#: The format ``configure_logging`` last installed, so a logger adopted later follows it.
_installed_format = "console"


def json_formatter() -> logging.Formatter:
    """Return a formatter that renders a stdlib record as one JSON object."""
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    )


def configure_logging(level: int | str | None = None, fmt: str | None = None) -> None:
    """Install one stdout handler for the whole process, replacing any existing one.

    Args:
        level: Threshold to install. Defaults to ``$REWIND_LOG_LEVEL``, then ``INFO``.
        fmt: ``console`` or ``json``. Defaults to ``$REWIND_LOG_FORMAT``, then ``console``.

    ``force`` is set so that a second entry point in the same process — a script
    importing the API app, for instance — still gets this configuration rather than
    silently keeping an earlier one.

    """
    global _installed_format
    chosen = fmt or os.environ.get("REWIND_LOG_FORMAT", "console")
    _installed_format = chosen
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(json_formatter() if chosen == "json" else logging.Formatter("%(message)s"))
    logging.basicConfig(
        level=level if level is not None else os.environ.get("REWIND_LOG_LEVEL", DEFAULT_LEVEL),
        handlers=[handler],
        force=True,
    )
    if chosen == "json":
        for name in _SELF_CONFIGURED:
            adopt_logger(name)


def adopt_logger(name: str) -> None:
    """Route a library logger that installs its own handler through the configured one.

    For libraries imported after ``configure_logging`` ran: Ultralytics creates its
    logger with a stdout handler when the detector first loads it, on the worker's first
    job, so no startup step can reach it. Only when ``configure_logging`` installed JSON;
    at a terminal the library's own output is what a person expects to read.
    """
    if _installed_format != "json":
        return
    library = logging.getLogger(name)
    library.handlers.clear()
    library.propagate = True
