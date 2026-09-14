"""Profile the pipeline end to end on rendered cases (E9.3).

Runs ``process_run`` exactly as the worker does, against the ephemeral Postgres in
``DATABASE_URL``, inside a transaction that is rolled back, so nothing it writes
survives. Reports wall-clock seconds per stage, frames per second through perception,
and peak memory. The roadmap allows parallelising streams only where this profile
shows a benefit; the point of the script is that the decision rests on a number.

    DATABASE_URL=postgresql+psycopg://t:t@localhost:5434/t
        uv run python scripts/evaluation/profile_run.py case_01 case_02
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import resource
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from apps.worker.settings import worker_settings
from apps.worker.tasks import build_detector, camera_offsets, robot_telemetry
from packages.database.session import make_engine
from services.ingestion import create_run
from services.observability.logging import configure_logging
from services.perception import process_run

log = logging.getLogger(__name__)

REPORTS = pathlib.Path("artifacts/benchmark-reports")


def peak_rss_mb() -> float:
    """Peak resident set size of this process so far, in megabytes (macOS reports bytes)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6


def accelerator_mb() -> float | None:
    """Memory the accelerator driver holds for this process, or None off MPS."""
    try:
        import torch

        if torch.backends.mps.is_available():
            return float(torch.mps.driver_allocated_memory()) / 1e6
    except ImportError:
        pass
    return None


def profile(case_id: str, session: Session, detector: Any, scene: dict[str, Any]) -> dict[str, Any]:
    """Process one case and return its timings."""
    case_dir = worker_settings.samples_dir / case_id
    clips = sorted(case_dir.glob("*.mp4"))
    run, _ = create_run(
        session,
        input_paths=clips,
        dataset_version="profile",
        config_version="profile",
        model_versions={"detector": detector.config.version},
    )
    started = time.perf_counter()
    result = process_run(
        session,
        run_id=run.run_id,
        case_dir=case_dir,
        camera_offsets=camera_offsets(),
        detector=detector,
        scene=scene,
        telemetry=robot_telemetry(run.run_id, case_id),
    )
    total = time.perf_counter() - started
    perception = sum(v for k, v in result.stages_s.items() if k.startswith("perception:"))
    return {
        "case_id": case_id,
        "frames": result.frames_processed,
        "total_s": round(total, 2),
        "perception_s": round(perception, 2),
        "fps": round(result.frames_processed / perception, 1) if perception else None,
        "stages_s": {k: round(v, 2) for k, v in result.stages_s.items()},
        "observations": result.observations,
        "events": result.events,
        "incidents": result.incidents,
        "peak_rss_mb": round(peak_rss_mb(), 0),
        "accelerator_mb": accelerator_mb(),
    }


def render(rows: list[dict[str, Any]], detector_load_s: float, device: str) -> str:
    """Render the profile as markdown."""
    lines = [
        "# Pipeline profile — E9.3",
        "",
        f"- **Generated:** {datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        f"- **Device:** `{device}`; detector load {detector_load_s:.1f} s, once per worker",
        "- **Method:** `process_run` as the worker calls it, one case at a time, rolled back",
        "",
        "| Case | Frames | Total s | Perception s | FPS | Persist s | Events s | Identity s "
        "| Reasoning s | Incidents | Peak RSS MB | Accelerator MB |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        st = r["stages_s"]
        acc = "—" if r["accelerator_mb"] is None else f"{r['accelerator_mb']:.0f}"
        lines.append(
            f"| `{r['case_id']}` | {r['frames']} | {r['total_s']} | {r['perception_s']} | "
            f"{r['fps']} | {st.get('persist:observations', 0)} | {st.get('events', 0)} | "
            f"{st.get('identity', 0)} | {st.get('reasoning', 0)} | {r['incidents']} | "
            f"{r['peak_rss_mb']:.0f} | {acc} |"
        )
    lines.append("")
    lines.append("Per-camera perception seconds (decode, detect, track, describe):")
    lines.append("")
    for r in rows:
        cams = {k.split(":")[1]: v for k, v in r["stages_s"].items() if k.startswith("perception:")}
        lines.append(f"- `{r['case_id']}`: {cams}")
    return "\n".join(lines) + "\n"


def main() -> int:
    """Profile each requested case and write the report."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="+")
    args = parser.parse_args()

    started = time.perf_counter()
    detector = build_detector()
    detector_load_s = time.perf_counter() - started
    scene = json.loads(worker_settings.scene_config.read_text())

    engine = make_engine()
    rows: list[dict[str, Any]] = []
    for case_id in args.cases:
        connection = engine.connect()
        transaction = connection.begin()
        try:
            rows.append(profile(case_id, Session(bind=connection), detector, scene))
        finally:
            transaction.rollback()
            connection.close()
        log.info("%s", rows[-1])

    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"profile-{stamp}.json").write_text(json.dumps(rows, indent=2))
    (REPORTS / f"profile-{stamp}.md").write_text(
        render(rows, detector_load_s, worker_settings.detector_device)
    )
    log.info("written to %s", REPORTS / f"profile-{stamp}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
