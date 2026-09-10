"""Report how far the render has got and how long is left.

Reads the render log rather than counting files. A video file exists from the moment
Blender opens it for writing, so counting ``*.mp4`` reports a camera as finished
while it is still ten minutes from done. The log's completion lines are the only
honest signal.

    make render-eta
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from services.observability.logging import configure_logging

log = logging.getLogger(__name__)

LOG_PATH = Path("artifacts/render.log")
FRAMES_PER_CAMERA = 450
CAMERAS_PER_CASE = 3

CASE_START = re.compile(r"^\[(\d+)/(\d+)\] (case_\d+) — (.+?) \((\d+) frames\)")
CASE_SKIP = re.compile(r"^\[(\d+)/(\d+)\] (case_\d+) — already rendered")
CAMERA_START = re.compile(r"rendering (CAM_\w+) \((\d+)/(\d+)\)")
CAMERA_DONE = re.compile(r"finished (CAM_\w+)")
PROGRESS = re.compile(r"(CAM_\w+) (\d+)/(\d+) frames \((\d+)%\) ([\d.]+) fps")


@dataclass
class RenderProgress:
    """A snapshot of where the render has got to."""

    cases_total: int = 0
    cases_skipped: int = 0
    current_case: str = ""
    cameras_done: int = 0
    current_camera: str = ""
    frames_done: int = 0
    frames_total: int = FRAMES_PER_CAMERA
    fps: float = 0.0
    running: bool = False

    @property
    def cameras_total(self) -> int:
        """Cameras this run has to render, excluding skipped cases."""
        return (self.cases_total - self.cases_skipped) * CAMERAS_PER_CASE

    @property
    def frames_remaining(self) -> int:
        """Frames left across every camera still to do.

        The in-flight camera contributes only its unfinished frames; the ones after
        it contribute a full pass each.
        """
        after_current = max(0, self.cameras_total - self.cameras_done - 1)
        in_flight = max(0, self.frames_total - self.frames_done)
        return after_current * FRAMES_PER_CAMERA + in_flight

    @property
    def seconds_remaining(self) -> float:
        """Estimated seconds left, or 0.0 when no rate is known yet."""
        if self.fps <= 0:
            return 0.0
        return self.frames_remaining / self.fps

    @property
    def percent(self) -> int:
        """Overall completion across the whole run."""
        total = self.cameras_total * FRAMES_PER_CAMERA
        if total == 0:
            return 100
        done = self.cameras_done * FRAMES_PER_CAMERA + self.frames_done
        return min(100, int(done * 100 / total))


def is_running() -> bool:
    """Whether a render process is currently alive."""
    result = subprocess.run(["pgrep", "-f", "render_cases.py"], capture_output=True, text=True)
    return result.returncode == 0


def parse(text: str) -> RenderProgress:
    """Build a progress snapshot from the render log."""
    progress = RenderProgress(running=is_running())
    for line in text.splitlines():
        if match := CASE_SKIP.search(line):
            progress.cases_total = int(match.group(2))
            progress.cases_skipped += 1
        elif match := CASE_START.search(line):
            progress.cases_total = int(match.group(2))
            progress.current_case = match.group(3)
            progress.frames_total = int(match.group(5))
        elif match := CAMERA_START.search(line):
            progress.current_camera = match.group(1)
            progress.frames_done = 0
        elif CAMERA_DONE.search(line):
            progress.cameras_done += 1
            progress.frames_done = 0
        elif match := PROGRESS.search(line):
            progress.current_camera = match.group(1)
            progress.frames_done = int(match.group(2))
            progress.frames_total = int(match.group(3))
            progress.fps = float(match.group(5))
    return progress


def human(seconds: float) -> str:
    """Format a duration the way someone waiting for it would read it."""
    if seconds <= 0:
        return "unknown"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60}h {minutes % 60:02d}m"


def main() -> int:
    """Print the render progress and estimated time remaining."""
    configure_logging()
    if not LOG_PATH.exists():
        log.info("No render log at %s. Start one with `make render`.", LOG_PATH)
        return 1

    progress = parse(LOG_PATH.read_text())
    age = time.time() - LOG_PATH.stat().st_mtime

    log.info("Render progress")
    log.info(
        "  cases        %s of %s (%s skipped as already rendered)",
        progress.cameras_done // CAMERAS_PER_CASE + progress.cases_skipped,
        progress.cases_total,
        progress.cases_skipped,
    )
    log.info("  cameras      %s of %s complete", progress.cameras_done, progress.cameras_total)
    if progress.current_camera:
        log.info(
            "  in flight    %s %s, frame %s of %s",
            progress.current_case,
            progress.current_camera,
            progress.frames_done,
            progress.frames_total,
        )
    log.info("  overall      %s%%", progress.percent)
    log.info("  rate         %.1f frames/sec", progress.fps)
    log.info("  TIME LEFT    %s", human(progress.seconds_remaining))

    if not progress.running:
        log.info("")
        log.info("  No render process is alive. It finished, or it stopped early.")
    elif age > 120:
        # The log is appended every 25 frames, so silence for two minutes on a
        # sub-1-fps render means the process is wedged rather than merely slow.
        log.info("")
        log.info("  Warning: the log has not been written to for %s.", human(age))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
