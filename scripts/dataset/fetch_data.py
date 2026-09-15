"""Fetch the rendered cases and the detector weights a fresh clone needs (E10.1).

Both are gitignored: the footage is 38 MB of rendered video and the weights are a
trained artefact, and neither belongs in version control. They are published once as
the ``data-v1.1`` release asset and checked here against what the repository already
records: every clip and annotation against ``data/manifests/v1.json`` (E1.3), the
weights against ``ml/models/yolo11n-rewind-v3/best.pt.sha256``. A download that does
not match is reported file by file and fails, so a corrupted or substituted asset can
never be processed as if it were the benchmark data.

Nothing is downloaded when everything already verifies. Needs the GitHub CLI with
access to the repository (``gh auth login``).

    make fetch-data
"""

from __future__ import annotations

import json
import logging
import pathlib
import subprocess
import tarfile
import tempfile

from scripts.dataset.make_manifest import sha256
from services.observability.logging import configure_logging

log = logging.getLogger(__name__)

RELEASE = "data-v1.1"
ASSET = "rewind-data-v1.1.tar.gz"
MANIFEST = pathlib.Path("data/manifests/v1.1.json")
SAMPLES = pathlib.Path("data/samples")
WEIGHTS = pathlib.Path("ml/models/yolo11n-rewind-v3/best.pt")
WEIGHTS_SUM = pathlib.Path("ml/models/yolo11n-rewind-v3/best.pt.sha256")


def problems() -> list[str]:
    """Every expected file that is missing or does not match its recorded checksum."""
    found: list[str] = []
    manifest = json.loads(MANIFEST.read_text())
    expected = [(SAMPLES / f["path"], f["sha256"]) for c in manifest["cases"] for f in c["files"]]
    expected.append((WEIGHTS, WEIGHTS_SUM.read_text().split()[0]))
    for path, digest in expected:
        if not path.exists():
            found.append(f"missing: {path}")
        elif sha256(path) != digest:
            found.append(f"checksum mismatch: {path}")
    return found


def main() -> int:
    """Download and unpack the release asset unless everything already verifies."""
    configure_logging()
    if not problems():
        log.info("rendered cases and detector weights already present and verified")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        try:
            subprocess.run(
                ["gh", "release", "download", RELEASE, "--pattern", ASSET, "--dir", tmp],
                check=True,
            )
        except FileNotFoundError:
            log.error("the GitHub CLI is not installed: https://cli.github.com, then gh auth login")
            return 1
        except subprocess.CalledProcessError:
            log.error("could not download %s from release %s; run gh auth login", ASSET, RELEASE)
            return 1
        with tarfile.open(pathlib.Path(tmp) / ASSET) as archive:
            archive.extractall(".", filter="data")
    remaining = problems()
    for problem in remaining:
        log.error("%s", problem)
    if remaining:
        return 1
    log.info("fetched and verified %s: rendered cases and detector weights", RELEASE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
