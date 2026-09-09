"""Freeze the API contract to openapi.json.

Run after any change to apps/api. The committed file is what the frontend and the
mock server are built against, so a drift between it and the app is a contract bug.

    uv run python scripts/export_openapi.py
"""

from __future__ import annotations

import json
import logging
import pathlib
import sys

from apps.api.main import app
from services.observability.logging import configure_logging

log = logging.getLogger(__name__)

OUT = pathlib.Path("openapi.json")


def main() -> int:
    """Write or verify openapi.json; return a process exit code."""
    spec = app.openapi()
    rendered = json.dumps(spec, indent=2, sort_keys=True) + "\n"

    if "--check" in sys.argv:
        if not OUT.exists():
            log.info("openapi.json is missing — run without --check to generate it.")
            return 1
        if OUT.read_text() != rendered:
            log.info("openapi.json is stale. Regenerate it and commit the result.")
            return 1
        log.info("openapi.json is current.")
        return 0

    OUT.write_text(rendered)
    paths = len(spec.get("paths", {}))
    log.info(f"wrote {OUT} — {paths} paths, API v{spec['info']['version']}")
    return 0


if __name__ == "__main__":
    configure_logging()
    raise SystemExit(main())
