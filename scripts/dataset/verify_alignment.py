"""Verify that rendered video and ground truth describe the same motion.

Ground truth is ray-cast from the scene; video is rendered from it. Nothing forces
the two to agree, and once they did not: actors were keyframed for the scrubbable
scene export but not for the video render, so 18 clips shipped with every actor
parked at its final position while the labels moved through the case. Two full
renders, a manifest and a baseline evaluation all passed. The first symptom was a
fine-tuned detector scoring 0.08 mAP on boxes.

The check is direct. Each entity class has a distinct colour, chosen in E1.1 to be
separable from every surface. For a sample of frames, the pixels inside each ground
truth box must be dominated by that entity's colour. If the box is empty of it, the
label and the pixels disagree, and nothing trained on them can be trusted.

    make verify-alignment
"""

from __future__ import annotations

import argparse
import colorsys
import json
import logging
import pathlib
from dataclasses import dataclass

import cv2
import numpy as np

from packages.common.color import linear_to_srgb
from services.ingestion import decode_frames
from services.observability.logging import configure_logging

log = logging.getLogger(__name__)

SAMPLES = pathlib.Path("data/samples")
SCENE = pathlib.Path("ml/configs/scene_v1.json")

#: Frames sampled per camera. Spread across the clip so a freeze at any point is seen.
SAMPLE_FRAMES = [30, 135, 250, 400]

#: Fraction of a box's pixels that must be within tolerance of the entity colour. A
#: box is tight around a solid-colour primitive, so most pixels should match; the
#: allowance covers shading, edges and partial occlusion at the visibility floor.
MIN_MATCH_FRACTION = 0.35

#: Per-channel tolerance in 8-bit sRGB. Deliberately loose: the area lights shade a
#: flat white robot down to roughly [180,180,180] from its configured [249,241,240],
#: a 70-point shift on a correctly placed box. At 70 that read as a failure. The
#: entity classes differ by well over 100 in at least one channel from each other
#: and from every surface, so 100 cannot mistake one for another; what it can still
#: catch is a box containing none of its entity at all, which is the bug it exists
#: for and reads as a 0% match either way.
TOLERANCE = 100

#: Hue window, degrees either side of the entity's configured hue, for the second
#: match path. Shading moves a surface's brightness and saturation but barely its
#: hue: a forklift filling the near field renders a washed-out pink top and a
#: near-black flank, both outside ±100 RGB of the base red and both within 8 degrees
#: of its hue. Measured on the first correct render, 8 passed every box (worst 0.58)
#: while 4 did not; 12 would let forklift (13 deg) and pallet (24 deg) share a centre.
HUE_TOLERANCE_DEG = 8

#: Saturation floor (0-1) below which a pixel has no meaningful hue and the hue path
#: is skipped. Excludes concrete, wall and every shadow; disables the path entirely
#: for the achromatic robot, which keeps the RGB tolerance alone.
MIN_SATURATION = 0.25

#: Share of a box's visible fraction that must match. A box is drawn around the whole
#: entity, occluded parts included, so an actor at visibility 0.18 behind another can
#: only ever colour 18% of it. With one colour per class the occluder's pixels passed
#: for the hidden actor's, which hid this; per-actor colours (P01 green, P02 orange)
#: exposed it as 17% and 29% matches on correctly placed boxes. A misplaced box still
#: reads near 0%, so half the visible fraction keeps the margin the bug needs.
VISIBLE_SHARE = 0.5


def required_fraction(
    box: tuple[int, int, int, int], visibility: float, width: int, height: int
) -> float | None:
    """Match fraction a box must reach, or None when it cannot be judged by colour.

    A box cut by the frame edge is skipped: what remains in frame is the near-field
    face at a grazing angle, washed out past both colour paths (P02's top face renders
    hue 12 against its 16, which is the pallet's hue, so widening the window would
    trade this false failure for a class collision). Measured on the colour-fix
    render, this skipped 3 of 94 sampled boxes and lost 1 of 27 simulated frozen-actor
    detections; interior boxes still catch the bug.
    """
    x1, y1, x2, y2 = box
    if x1 <= 0 or y1 <= 0 or x2 >= width or y2 >= height:
        return None
    return min(MIN_MATCH_FRACTION, VISIBLE_SHARE * visibility)


@dataclass
class Mismatch:
    """One ground-truth box whose pixels do not contain its entity."""

    case_id: str
    camera_id: str
    frame_index: int
    entity_id: str
    entity_class: str
    match_fraction: float


def srgb8(linear: list[float]) -> np.ndarray:
    """Convert a config colour (linear RGB) to 8-bit BGR as OpenCV decodes video."""
    rgb = [max(0, min(255, round(linear_to_srgb(c) * 255))) for c in linear]
    return np.array(rgb[::-1], dtype=np.int16)


def hue_sat(linear: list[float]) -> tuple[float, float]:
    """Hue in OpenCV's 0-180 scale and saturation 0-1 of a config colour."""
    h, s, _ = colorsys.rgb_to_hsv(*(min(1.0, linear_to_srgb(c)) for c in linear[:3]))
    return h * 180.0, s


def matches(crop: np.ndarray, target_bgr: np.ndarray, target_hs: tuple[float, float]) -> np.ndarray:
    """Per-pixel mask of pixels that read as the entity, by RGB closeness or by hue."""
    close = np.all(np.abs(crop.astype(np.int16) - target_bgr) <= TOLERANCE, axis=2)
    hue, sat = target_hs
    if sat < MIN_SATURATION:
        return np.asarray(close)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).astype(np.int16)
    # OpenCV hue wraps at 180; fold the difference into [-90, 90) before taking abs.
    d_hue = np.abs((hsv[..., 0] - hue + 90) % 180 - 90)
    by_hue = (d_hue <= HUE_TOLERANCE_DEG / 2) & (hsv[..., 1] >= MIN_SATURATION * 255)
    return np.asarray(close | by_hue)


def check_case(
    case_id: str, colours: dict[str, np.ndarray], hues: dict[str, tuple[float, float]]
) -> list[Mismatch]:
    """Check one case, returning every box whose entity colour is absent."""
    case_dir = SAMPLES / case_id
    truth = json.loads((case_dir / "observations_gt.json").read_text())
    by_key: dict[tuple[str, int], list[dict[str, object]]] = {}
    for row in truth:
        by_key.setdefault((str(row["camera_id"]), int(row["frame_index"])), []).append(row)

    mismatches: list[Mismatch] = []
    for clip in sorted(case_dir.glob("*.mp4")):
        camera_id = clip.stem
        wanted = [f for f in SAMPLE_FRAMES if (camera_id, f) in by_key]
        for frame_index, frame in decode_frames(clip, wanted):
            for row in by_key[(camera_id, frame_index)]:
                box = row["bbox"]
                assert isinstance(box, dict)
                x1, y1 = int(box["x1"]), int(box["y1"])
                x2, y2 = int(box["x2"]) + 1, int(box["y2"]) + 1
                crop = frame[y1:y2, x1:x2]
                height, width = frame.shape[:2]
                required = required_fraction(
                    (x1, y1, x2, y2), float(str(row["visibility"])), width, height
                )
                if crop.size == 0 or required is None:
                    continue
                key = str(row["entity_id"])
                if key not in colours:
                    key = str(row["entity_class"])
                fraction = float(matches(crop, colours[key], hues[key]).mean())
                if fraction < required:
                    mismatches.append(
                        Mismatch(
                            case_id,
                            camera_id,
                            frame_index,
                            str(row["entity_id"]),
                            str(row["entity_class"]),
                            fraction,
                        )
                    )
    return mismatches


def main() -> int:
    """Check every rendered case and return non-zero on any misalignment."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="*", help="case ids; default is every rendered case")
    args = parser.parse_args()

    scene = json.loads(SCENE.read_text())
    entities = {n: s for n, s in scene["entities"].items() if not n.startswith("_")}
    colours = {name: srgb8(spec["colour"]) for name, spec in entities.items()}
    hues = {name: hue_sat(spec["colour"]) for name, spec in entities.items()}
    # Actor overrides are keyed by entity id; the lookup in check_case tries the
    # entity id first and falls back to the class.
    for actor, value in scene.get("actor_colours", {}).items():
        if not actor.startswith("_"):
            colours[actor] = srgb8(value)
            hues[actor] = hue_sat(value)

    case_ids = args.cases or sorted(d.name for d in SAMPLES.glob("case_*") if any(d.glob("*.mp4")))
    if not case_ids:
        log.info("no rendered cases under %s", SAMPLES)
        return 1

    total = 0
    for case_id in case_ids:
        mismatches = check_case(case_id, colours, hues)
        if mismatches:
            log.info("%s  FAIL  %d box(es) do not contain their entity", case_id, len(mismatches))
            for m in mismatches[:6]:
                log.info(
                    "    %s frame %d %s (%s): only %.0f%% of the box is %s-coloured",
                    m.camera_id,
                    m.frame_index,
                    m.entity_id,
                    m.entity_class,
                    m.match_fraction * 100,
                    m.entity_class,
                )
            if len(mismatches) > 6:
                log.info("    ... and %d more", len(mismatches) - 6)
            total += len(mismatches)
        else:
            log.info("%s  ok", case_id)

    log.info("")
    if total:
        log.info("FAILED — %d misaligned box(es). The video and ground truth disagree.", total)
        log.info("Nothing trained or scored on this data can be trusted until it is re-rendered.")
        return 1
    log.info("OK — ground truth boxes contain their entities in every sampled frame.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
