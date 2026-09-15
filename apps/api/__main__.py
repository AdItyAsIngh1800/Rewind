"""Run the API: ``python -m apps.api`` (the container) or ``make api`` (development).

The process entry point, so it configures logging once, before the server starts.
uvicorn's own log configuration is disabled: it installs handlers that print plain text,
and it logs "Started server process" before any application hook runs, so those lines
would bypass the JSON formatter in an otherwise structured stream (E10.2).
"""

from __future__ import annotations

import argparse
import logging

import uvicorn

from apps.api.auth import USERS_VAR, configured_users
from services.observability.logging import configure_logging

log = logging.getLogger(__name__)


def main() -> int:
    """Parse the serving options and run uvicorn with this project's logging."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    configure_logging()
    # Refuse rather than serve an API nobody can sign in to: with no accounts every
    # request is a 401, which at the browser looks like a wrong password.
    if not configured_users():
        log.error(
            "%s is not set; no one could sign in. See docs/10-security-and-privacy.md", USERS_VAR
        )
        return 2
    uvicorn.run(
        "apps.api.main:app", host=args.host, port=args.port, reload=args.reload, log_config=None
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
