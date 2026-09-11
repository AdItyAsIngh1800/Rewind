"""Animate the actors, render the cases and export ground truth.

Run headlessly:

    blender --background data/scene/warehouse.blend \
        --python scripts/dataset/render_cases.py -- --case case_01

Runs inside Blender's bundled Python, so it imports nothing from this project. Every
number comes from ml/configs/scene_v1.json and ml/configs/cases_v1.json.

GROUND TRUTH COMES FROM RAY-CASTING, NOT FROM RENDER PASSES.

The obvious approach is to render the object-index pass and read back per-pixel object
ids. It was rejected for two reasons. Reading a pass headlessly depends on the
compositor Viewer node, which does not reliably update in background mode, and the
alternative of writing passes to disk was already ruled out by the disk budget in
docs/09-deployment.md.

Casting rays from the camera through a grid over each object's projected bounding box
answers the same two questions directly: which pixels actually see this object (giving
a tight, occlusion-aware box) and what fraction of it is visible. It is faster, it
works in background mode, and it decouples ground truth from rendering entirely, so
the annotations can be regenerated in seconds without re-rendering 8,100 frames.
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import pathlib
import sys
import time
from typing import Any

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

log = logging.getLogger(__name__)

BlenderObject = Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCENE_CONFIG = REPO_ROOT / "ml" / "configs" / "scene_v1.json"
CASES_CONFIG = REPO_ROOT / "ml" / "configs" / "cases_v1.json"
SAMPLES = REPO_ROOT / "data" / "samples"
SCENES = REPO_ROOT / "data" / "scene"

#: Rays cast across each object's projected box. 24x24 resolves a person at the far
#: end of the aisle to a few percent of visibility, which is finer than the 0.15
#: threshold the scene spec actually cares about.
RAY_GRID = 24

#: Scene spec section 7: below this, ground truth does not emit the entity at all.
#: Ground truth must not claim to see what a camera cannot.
MIN_VISIBILITY = 0.15


def script_args() -> argparse.Namespace:
    """Parse arguments after the ``--`` separator Blender passes through."""
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="all", help="case id, or 'all'")
    parser.add_argument("--frames", type=int, default=0, help="limit frames, 0 for all")
    parser.add_argument(
        "--gt-only",
        action="store_true",
        help="export ground truth without rendering video, for fast iteration",
    )
    parser.add_argument(
        "--save-blend",
        action="store_true",
        help=(
            "write a scrubbable .blend per case with the actors keyframed, instead "
            "of rendering. Open it in Blender to inspect occlusion and camera framing."
        ),
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="skip cases whose video is already rendered, so a run can be resumed",
    )
    return parser.parse_args(argv)


def already_rendered(case_id: str, camera_count: int) -> bool:
    """Whether a case already has video for every camera.

    Rendering is measured in tens of minutes per case, so a resumed run must not
    redo finished work. Checked by file count rather than a marker file: a marker
    can outlive the files it claims to describe.
    """
    return len(list((SAMPLES / case_id).glob("*.mp4"))) >= camera_count


# --------------------------------------------------------------------------
# Actors
# --------------------------------------------------------------------------


def spawn_actor(
    entity_id: str, entity_class: str, spec: dict[str, Any], index: int
) -> BlenderObject:
    """Create one actor primitive at its real-world footprint.

    Dimensions come from the scene config rather than being chosen for convenience,
    so a CC0 asset dropped in later scales into the same bounding volume and zone
    polygons never need re-checking because of the swap.
    """
    footprint = spec["footprint"]
    height = spec["height"]

    bpy.ops.mesh.primitive_cube_add(size=1.0)
    actor = bpy.context.active_object
    actor.name = entity_id
    actor.scale = (footprint[0], footprint[1], height)

    material = bpy.data.materials.new(f"MAT_{entity_id}")
    material.use_nodes = True
    material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (
        *spec["colour"],
        1.0,
    )
    actor.data.materials.append(material)

    # pass_index is not used for ground truth any more, but keeping it unique makes
    # the object identifiable if anyone does inspect a render pass by hand.
    actor.pass_index = index + 1
    actor["entity_id"] = entity_id
    actor["entity_class"] = entity_class
    return actor


def interpolate(waypoints: list[dict[str, Any]], t: float) -> tuple[float, float, str | None]:
    """Position and state at time ``t``, linear between waypoints.

    Linear rather than smoothed on purpose. At 10 FPS and walking speed the visual
    difference is negligible, and a closed-form position means ground truth is exactly
    reproducible from the config without replaying an animation system.
    """
    if t <= waypoints[0]["t"]:
        first = waypoints[0]
        return first["x"], first["y"], first.get("state")
    if t >= waypoints[-1]["t"]:
        last = waypoints[-1]
        return last["x"], last["y"], last.get("state")

    for start, end in itertools.pairwise(waypoints):
        if start["t"] <= t <= end["t"]:
            span = end["t"] - start["t"]
            ratio = 0.0 if span == 0 else (t - start["t"]) / span
            return (
                start["x"] + ratio * (end["x"] - start["x"]),
                start["y"] + ratio * (end["y"] - start["y"]),
                # State is a step function, not a blend: a robot is either moving or
                # stopped, never half stopped.
                start.get("state"),
            )
    last = waypoints[-1]
    return last["x"], last["y"], last.get("state")


def place_actors(
    case: dict[str, Any], actors: dict[str, BlenderObject], scene_cfg: dict[str, Any], t: float
) -> dict[str, str | None]:
    """Move every actor to its position at time ``t``; return their states."""
    states: dict[str, str | None] = {}
    for track in case["actors"]:
        actor = actors[track["entity_id"]]
        x, y, state = interpolate(track["waypoints"], t)
        height = scene_cfg["entities"][track["class"]]["height"]
        actor.location = (x, y, height / 2)
        states[track["entity_id"]] = state
    bpy.context.view_layer.update()
    return states


# --------------------------------------------------------------------------
# Ground truth by ray-casting
# --------------------------------------------------------------------------


def projected_box(
    camera: BlenderObject, actor: BlenderObject
) -> tuple[float, float, float, float] | None:
    """Project an actor's world bounding box into normalised camera space.

    Returns ``None`` when the actor is entirely behind or outside the frame, which
    saves casting a grid of rays that would all miss.
    """
    scene = bpy.context.scene
    xs: list[float] = []
    ys: list[float] = []
    for corner in actor.bound_box:
        world = actor.matrix_world @ Vector(corner)
        projected = world_to_camera_view(scene, camera, world)
        if projected.z <= 0:
            continue  # behind the camera
        xs.append(projected.x)
        ys.append(projected.y)

    if not xs:
        return None
    x0, x1 = max(0.0, min(xs)), min(1.0, max(xs))
    y0, y1 = max(0.0, min(ys)), min(1.0, max(ys))
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def observe(
    camera: BlenderObject, actor: BlenderObject, width: int, height: int
) -> tuple[tuple[float, float, float, float], float] | None:
    """Return the visible pixel box and visibility fraction for one actor.

    Rays are cast from the camera through a grid over the actor's projected box. A ray
    counts as seeing the actor only when the actor is the *first* thing it hits, so
    racking and other actors occlude correctly and the resulting box is the visible
    (modal) box a detector would be scored against, not the amodal one.
    """
    box = projected_box(camera, actor)
    if box is None:
        return None

    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    origin = camera.matrix_world.translation

    nx0, ny0, nx1, ny1 = box
    hits_x: list[float] = []
    hits_y: list[float] = []
    total = 0
    seen = 0

    for i in range(RAY_GRID):
        for j in range(RAY_GRID):
            u = nx0 + (nx1 - nx0) * (i + 0.5) / RAY_GRID
            v = ny0 + (ny1 - ny0) * (j + 0.5) / RAY_GRID
            total += 1

            # Reconstruct a world-space ray through this normalised camera point.
            frame = camera.data.view_frame(scene=scene)
            top_left = camera.matrix_world @ frame[3]
            top_right = camera.matrix_world @ frame[0]
            bottom_left = camera.matrix_world @ frame[2]
            target = top_left + (top_right - top_left) * u + (bottom_left - top_left) * (1.0 - v)
            direction = (target - origin).normalized()

            hit, _location, _normal, _index, obj, _matrix = scene.ray_cast(
                depsgraph, origin, direction
            )
            if hit and obj is not None and obj.name == actor.name:
                seen += 1
                hits_x.append(u)
                hits_y.append(v)

    if not hits_x or total == 0:
        return None

    visibility = seen / total
    # Pixel box from the rays that actually landed on the actor. Blender's v axis runs
    # bottom-up; image coordinates run top-down.
    x1_px = min(hits_x) * width
    x2_px = max(hits_x) * width
    y1_px = (1.0 - max(hits_y)) * height
    y2_px = (1.0 - min(hits_y)) * height

    # A single-ray hit has no extent. Give it one pixel so the box stays valid rather
    # than being silently dropped by the contract's degenerate-box check.
    if x2_px - x1_px < 1.0:
        x2_px = x1_px + 1.0
    if y2_px - y1_px < 1.0:
        y2_px = y1_px + 1.0

    return (x1_px, y1_px, x2_px, y2_px), visibility


# --------------------------------------------------------------------------
# Zones and events
# --------------------------------------------------------------------------


def in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    """Ray-crossing point-in-polygon test."""
    inside = False
    count = len(polygon)
    for i in range(count):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % count]
        if (y1 > y) != (y2 > y):
            crossing = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
            if x < crossing:
                inside = not inside
    return inside


def derive_events(
    case: dict[str, Any], scene_cfg: dict[str, Any], fps: int, frames: int
) -> list[dict[str, Any]]:
    """Derive the annotated event timeline from the actor scripts.

    Derived rather than hand-written so it cannot disagree with the motion that was
    actually rendered. These are annotations of what *happened*, independent of what
    any camera saw: an event here that no camera observed is exactly the case the
    system must not claim to have seen.
    """
    events: list[dict[str, Any]] = []
    zones = scene_cfg["zones"]
    membership: dict[tuple[str, str], bool] = {}
    states: dict[str, str | None] = {}
    counter = 0

    for frame in range(frames):
        t = frame / fps
        for track in case["actors"]:
            entity = track["entity_id"]
            x, y, state = interpolate(track["waypoints"], t)

            for zone in zones:
                key = (entity, zone["id"])
                now = in_polygon(x, y, zone["polygon"])
                before = membership.get(key, False)
                if now != before:
                    counter += 1
                    events.append(
                        {
                            "event_id": f"GT-EVT-{counter:04d}",
                            "run_id": "GT",
                            "event_type": "zone_entry" if now else "zone_exit",
                            "timestamp_s": round(t, 3),
                            "camera_id": None,
                            "entity_ids": [entity],
                            "zone_id": zone["id"],
                            "confidence": 1.0,
                            "evidence_refs": [],
                            "payload": {"x": round(x, 3), "y": round(y, 3)},
                        }
                    )
                    membership[key] = now

            if state is not None and states.get(entity) != state:
                if states.get(entity) is not None:
                    counter += 1
                    events.append(
                        {
                            "event_id": f"GT-EVT-{counter:04d}",
                            "run_id": "GT",
                            "event_type": "state_change",
                            "timestamp_s": round(t, 3),
                            "camera_id": None,
                            "entity_ids": [entity],
                            "zone_id": None,
                            "confidence": 1.0,
                            "evidence_refs": [],
                            "payload": {"from": states[entity], "to": state, "source": "telemetry"},
                        }
                    )
                states[entity] = state

    return events


# --------------------------------------------------------------------------
# Rendering and export
# --------------------------------------------------------------------------


_progress_state: dict[str, Any] = {}


def _on_frame_rendered(scene: BlenderObject, _depsgraph: BlenderObject = None) -> None:
    """Print a progress line as each frame completes.

    Blender's own per-frame chatter goes to stderr and is easy to lose in a log. A
    single predictable line per interval is what makes `tail -f` useful while a
    multi-hour render is running.
    """
    state = _progress_state
    if not state:
        return
    done = scene.frame_current - scene.frame_start + 1
    total = state["total"]
    if done % 25 and done != total:
        return
    elapsed = time.time() - state["started"]
    rate = done / elapsed if elapsed > 0 else 0.0
    remaining = (total - done) / rate if rate > 0 else 0.0
    log.info(
        f"      {state['camera']} {done}/{total} frames "
        f"({done * 100 // total}%) {rate:.1f} fps, about {remaining / 60:.0f} min left",
    )


def attach_progress(camera: str, total: int) -> None:
    """Start reporting progress for one camera."""
    _progress_state.update({"camera": camera, "total": total, "started": time.time()})
    bpy.app.handlers.render_post.append(_on_frame_rendered)


def detach_progress() -> None:
    """Stop reporting progress and clear the handler.

    Removed explicitly rather than left attached: handlers persist for the life of
    the Blender session, and a stale one would report the previous camera's totals
    against the next camera's frames.
    """
    if _on_frame_rendered in bpy.app.handlers.render_post:
        bpy.app.handlers.render_post.remove(_on_frame_rendered)
    _progress_state.clear()


def keyframe_actors(
    case: dict[str, Any],
    actors: dict[str, BlenderObject],
    scene_cfg: dict[str, Any],
    fps: int,
    frames: int,
) -> None:
    """Bake actor motion into keyframes so the timeline can be scrubbed.

    The renderer positions actors per frame in Python and never keyframes them, which
    is fine for producing images but leaves a saved .blend showing an empty
    warehouse. Baking the motion makes a case inspectable: open it in Blender, scrub
    the timeline, and look through each camera to see exactly what will be rendered.

    That matters for one job the scene spec calls for explicitly and no script can
    do: checking by eye that no pallet edge is visible under the racking.
    """
    # Motion between waypoints is linear, so the keyframes must be too. Blender
    # defaults to Bezier easing, which rounds every corner and would put an actor
    # somewhere the ground truth says it is not. Setting the preference before
    # inserting avoids walking F-curves afterwards, whose API moved to slotted
    # actions in Blender 4.4 and would need a version branch.
    preferences = bpy.context.preferences.edit
    previous = preferences.keyframe_new_interpolation_type
    preferences.keyframe_new_interpolation_type = "LINEAR"
    try:
        for track in case["actors"]:
            actor = actors[track["entity_id"]]
            height = scene_cfg["entities"][track["class"]]["height"]
            for frame in range(frames):
                x, y, _state = interpolate(track["waypoints"], frame / fps)
                actor.location = (x, y, height / 2)
                actor.keyframe_insert(data_path="location", frame=frame + 1)
    finally:
        preferences.keyframe_new_interpolation_type = previous


def configure_video_output(scene: BlenderObject) -> None:
    """Configure H.264 video output across Blender versions.

    Blender 5 split image and video output behind ``image_settings.media_type``;
    before that, ``FFMPEG`` was simply one of the file_format values. Setting the
    switch when it exists keeps this working on both without pinning a Blender
    version the render farm may not have.
    """
    settings = scene.render.image_settings
    if hasattr(settings, "media_type"):
        settings.media_type = "VIDEO"
    settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    # Constant rate factor rather than a bitrate target: the scene is mostly static
    # concrete, and a fixed bitrate would waste space on frames that do not change.
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"


def render_case(
    case: dict[str, Any],
    scene_cfg: dict[str, Any],
    cases_cfg: dict[str, Any],
    frames: int,
    gt_only: bool,
    save_blend: bool = False,
) -> dict[str, Any]:
    """Render one case from every camera and export its ground truth."""
    scene = bpy.context.scene
    fps = cases_cfg["fps"]
    out_dir = SAMPLES / case["id"]
    out_dir.mkdir(parents=True, exist_ok=True)

    actors = {
        track["entity_id"]: spawn_actor(
            track["entity_id"], track["class"], scene_cfg["entities"][track["class"]], index
        )
        for index, track in enumerate(case["actors"])
    }

    cameras = [bpy.data.objects[spec["id"]] for spec in scene_cfg["cameras"]]
    width = scene_cfg["camera_optics"]["resolution_x"]
    height = scene_cfg["camera_optics"]["resolution_y"]

    observations: list[dict[str, Any]] = []
    gaps: dict[str, list[list[float]]] = {}
    counter = 0

    for frame in range(frames):
        t = frame / fps
        # The returned states drive the telemetry channel, which becomes
        # state_change events in derive_events rather than a field on Observation.
        # Nothing here needs them, so the return is deliberately discarded.
        place_actors(case, actors, scene_cfg, t)

        for camera in cameras:
            for track in case["actors"]:
                entity = track["entity_id"]
                result = observe(camera, actors[entity], width, height)
                if result is None:
                    continue
                (x1, y1, x2, y2), visibility = result
                if visibility < MIN_VISIBILITY:
                    continue

                counter += 1
                x, y, _state = interpolate(track["waypoints"], t)
                observations.append(
                    {
                        "observation_id": f"GT-{case['id']}-{counter:06d}",
                        "run_id": "GT",
                        "camera_id": camera.name,
                        "frame_index": frame,
                        "timestamp_s": round(t, 3),
                        "entity_class": track["class"],
                        "bbox": {
                            "x1": round(x1, 2),
                            "y1": round(y1, 2),
                            "x2": round(x2, 2),
                            "y2": round(y2, 2),
                        },
                        "confidence": 1.0,
                        "track_id": f"{camera.name}-{entity}",
                        "entity_id": entity,
                        "world_xyz": [
                            round(x, 3),
                            round(y, 3),
                            round(scene_cfg["entities"][track["class"]]["height"] / 2, 3),
                        ],
                        "visibility": round(visibility, 3),
                    }
                )

        # Track intervals where an entity is visible to no camera at all. This is the
        # ground truth the uncertainty engine is scored against, and without it the
        # occlusion case cannot be evaluated.
        for track in case["actors"]:
            entity = track["entity_id"]
            seen_now = any(
                o["entity_id"] == entity and o["frame_index"] == frame for o in observations[-40:]
            )
            if not seen_now:
                gaps.setdefault(entity, []).append([round(t, 3), round(t + 1 / fps, 3)])

        if frame % 50 == 0:
            log.info(f"    frame {frame}/{frames}  observations {len(observations)}")

    # Keyframe the actors before ANY animated output, not only when saving a
    # scrubbable scene. The ground-truth loop above positions actors directly per
    # frame and never keyframes them, so an animation render without this step plays
    # 450 frames of actors parked wherever the loop last left them. That exact bug
    # shipped: the labels moved, the video did not, and the first sign was a
    # fine-tuned detector scoring 0.08 mAP on boxes.
    if save_blend or not gt_only:
        keyframe_actors(case, actors, scene_cfg, fps, frames)

    if save_blend:
        scene.frame_start = 1
        scene.frame_end = frames
        scene.camera = cameras[0]
        target = SCENES / f"{case['id']}.blend"
        target.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(target), copy=True)
        log.info(f"    scrubbable scene: {target}")

    if not gt_only and not save_blend:
        configure_video_output(scene)
        for position, camera in enumerate(cameras, start=1):
            scene.camera = camera
            scene.frame_start = 1
            scene.frame_end = frames
            scene.render.filepath = str(out_dir / f"{camera.name}.mp4")
            log.info(
                f"    rendering {camera.name} ({position}/{len(cameras)}) {frames} frames",
            )
            attach_progress(camera.name, frames)
            try:
                bpy.ops.render.render(animation=True)
            finally:
                detach_progress()
            log.info(f"    finished {camera.name}")

    return {"observations": observations, "gaps": gaps, "actors": actors}


def merge_gaps(intervals: list[list[float]]) -> list[list[float]]:
    """Collapse per-frame invisible spans into contiguous intervals."""
    if not intervals:
        return []
    merged = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start <= merged[-1][1] + 1e-6:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return merged


def export(case: dict[str, Any], result: dict[str, Any], events: list[dict[str, Any]]) -> None:
    """Write every ground-truth artefact for one case."""
    out_dir = SAMPLES / case["id"]

    def write(name: str, payload: Any) -> None:
        (out_dir / name).write_text(json.dumps(payload, indent=2) + "\n")

    write("observations_gt.json", result["observations"])
    write("events_gt.json", events)
    write(
        "identities_gt.json",
        {
            track["entity_id"]: [
                f"{cam}-{track['entity_id']}" for cam in ("CAM_A", "CAM_B", "CAM_C")
            ]
            for track in case["actors"]
        },
    )
    write("cause_gt.json", {"incident_class": case["incident_class"], "cause": case["cause_gt"]})
    write(
        "gaps_gt.json",
        {entity: merge_gaps(spans) for entity, spans in result["gaps"].items()},
    )


def main() -> int:
    """Render the requested cases and export their ground truth."""
    args = script_args()
    scene_cfg = json.loads(SCENE_CONFIG.read_text())
    cases_cfg = json.loads(CASES_CONFIG.read_text())

    fps = cases_cfg["fps"]
    total_frames = int(cases_cfg["duration_s"] * fps)
    frames = args.frames or total_frames

    selected = [c for c in cases_cfg["cases"] if args.case == "all" or c["id"] == args.case]
    if not selected:
        log.info(f"no case matching {args.case!r}")
        return 1

    camera_count = len(scene_cfg["cameras"])
    for index, case in enumerate(selected, start=1):
        if args.skip_existing and not args.gt_only and already_rendered(case["id"], camera_count):
            log.info(f"\n[{index}/{len(selected)}] {case['id']} — already rendered, skipping")
            continue
        log.info(f"\n[{index}/{len(selected)}] {case['id']} — {case['name']} ({frames} frames)")
        result = render_case(case, scene_cfg, cases_cfg, frames, args.gt_only, args.save_blend)
        events = derive_events(case, scene_cfg, fps, frames)
        export(case, result, events)
        log.info(f"  observations : {len(result['observations'])}")
        log.info(f"  events       : {len(events)}")
        log.info(f"  written to   : {SAMPLES / case['id']}")

        for actor in result["actors"].values():
            bpy.data.objects.remove(actor, do_unlink=True)

    return 0


if __name__ == "__main__":
    # Blender runs its own bundled Python, so services.observability.logging is not
    # importable here. Same handler, spelled out rather than shared.
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    raise SystemExit(main())
