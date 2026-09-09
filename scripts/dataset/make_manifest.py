"""Generate the dataset manifest.

The rendered media is gitignored because it is large. The manifest is therefore the
committed record of what the dataset *was* for a given version: which files existed,
what they hashed to, where they came from and which split each case belongs to.

Without it, a benchmark number six weeks from now cannot be tied to the data that
produced it, and "the dataset changed" becomes an unfalsifiable explanation for any
regression.

    uv run python scripts/dataset/make_manifest.py --dataset-version v1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import pathlib
from datetime import UTC, datetime
from typing import Any

from services.observability.logging import configure_logging

log = logging.getLogger(__name__)

SAMPLES = pathlib.Path("data/samples")
MANIFESTS = pathlib.Path("data/manifests")

#: Charter §3: four tuning cases, two held out. The golden pair is not opened until
#: E9.1 in Week 17, and no golden frame may enter any training or validation split.
SPLITS: dict[str, str] = {
    "case_01": "tune",
    "case_02": "golden",
    "case_03": "tune",
    "case_04": "tune",
    "case_05": "tune",
    "case_06": "golden",
}

#: Provenance for the whole dataset. Simulated footage has no third-party licence and
#: no privacy surface, which is one of the reasons it was chosen.
PROVENANCE: dict[str, str] = {
    "source": "Simulated in Blender from docs/dataset/scene-spec.md",
    "licence": "CC0-1.0 (original work, no third-party footage)",
    "contains_real_people": "no",
    "consent_required": "no",
}


def sha256(path: pathlib.Path, chunk: int = 1 << 20) -> str:
    """Hash one file, streaming so a large video does not land in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def describe_case(directory: pathlib.Path) -> dict[str, Any]:
    """Describe one case directory: its files, their hashes and its split."""
    files = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        files.append(
            {
                "path": path.relative_to(SAMPLES).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    split = SPLITS.get(directory.name, "unassigned")
    return {
        "case": directory.name,
        "split": split,
        "file_count": len(files),
        "total_bytes": sum(f["bytes"] for f in files),
        "files": files,
    }


def build(dataset_version: str) -> dict[str, Any]:
    """Build the manifest for everything currently under data/samples."""
    cases = [describe_case(d) for d in sorted(SAMPLES.iterdir()) if d.is_dir()]
    unassigned = [c["case"] for c in cases if c["split"] == "unassigned"]

    return {
        "dataset_version": dataset_version,
        "generated_at": datetime.now(UTC).isoformat(),
        "scene_spec": "docs/dataset/scene-spec.md",
        "provenance": PROVENANCE,
        "split_policy": {
            "tune": sorted(k for k, v in SPLITS.items() if v == "tune"),
            "golden": sorted(k for k, v in SPLITS.items() if v == "golden"),
            "rule": (
                "No golden-case frame may appear in any training or validation split. "
                "Asserted on case ids, never checked by eye."
            ),
        },
        "warnings": ([f"case {c} has no split assigned" for c in unassigned] if unassigned else []),
        "case_count": len(cases),
        "total_bytes": sum(c["total_bytes"] for c in cases),
        "cases": cases,
    }


def main() -> int:
    """Write the manifest and print a summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-version", default="v1")
    parser.add_argument("--out", type=pathlib.Path, default=None)
    args = parser.parse_args()

    if not SAMPLES.exists() or not any(SAMPLES.iterdir()):
        log.info(f"No rendered cases under {SAMPLES}. Run `make render` first.")
        return 1

    manifest = build(args.dataset_version)
    target = args.out or MANIFESTS / f"{args.dataset_version}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    megabytes = manifest["total_bytes"] / 1048576
    log.info(f"{target}")
    log.info(f"  dataset version : {manifest['dataset_version']}")
    log.info(f"  cases           : {manifest['case_count']}")
    log.info(f"  total size      : {megabytes:.1f} MB")
    for warning in manifest["warnings"]:
        log.info(f"  WARNING: {warning}")
    return 0


if __name__ == "__main__":
    configure_logging()
    raise SystemExit(main())
