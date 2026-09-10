"""Build the REWIND warehouse scene in Blender.

Run headlessly:

    blender --background --python scripts/dataset/build_scene.py -- --out data/scene/warehouse.blend

This script runs inside Blender's own bundled Python. It cannot import anything from
this project, so every dimension is read from ml/configs/scene_v1.json rather than
duplicated here. If a number looks wrong, fix the config, not this file.

Entities are primitives for now, authored at the real object's footprint rather than
at a convenient box size. A CC0 asset dropped in later scales into the same bounding
volume, so zone polygons and camera coverage never need re-checking because of the
swap.
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
from typing import Any

import bpy
from mathutils import Vector

log = logging.getLogger(__name__)

# Blender's own types cannot be imported into this project's environment, so bpy
# objects are annotated as Any. Naming the reason here is better than scattering

BlenderObject = Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "ml" / "configs" / "scene_v1.json"


def script_args() -> argparse.Namespace:
    """Parse arguments after the ``--`` separator Blender uses to pass them through."""
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--out", type=pathlib.Path, default=REPO_ROOT / "data/scene/warehouse.blend"
    )
    return parser.parse_args(argv)


def clear_scene() -> None:
    """Remove everything Blender starts with.

    A fresh file ships a cube, a camera and a light. Leaving them produces a stray
    object in the object-index pass and therefore a phantom entity in ground truth.
    """
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for block in list(collection):
            collection.remove(block)


def make_material(
    name: str, rgb: tuple[float, float, float], roughness: float = 0.8
) -> BlenderObject:
    """Create a simple diffuse material.

    Deliberately plain. Physically-accurate shading buys realism the detector does not
    use, and every extra shader node is render time spent on 8,100 frames.
    """
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    return material


def add_box(
    name: str,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    height: float,
    material: BlenderObject,
    z_base: float = 0.0,
) -> BlenderObject:
    """Add an axis-aligned box spanning the given world ranges."""
    size_x = x_range[1] - x_range[0]
    size_y = y_range[1] - y_range[0]
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    box = bpy.context.active_object
    box.name = name
    box.scale = (size_x, size_y, height)
    box.location = (
        (x_range[0] + x_range[1]) / 2,
        (y_range[0] + y_range[1]) / 2,
        z_base + height / 2,
    )
    box.data.materials.append(material)
    return box


def build_shell(config: dict[str, Any], materials: dict[str, BlenderObject]) -> None:
    """Build floor, walls and ceiling."""
    house = config["warehouse"]
    width, depth, height = house["size_x"], house["size_y"], house["height_z"]

    bpy.ops.mesh.primitive_plane_add(size=1.0)
    floor = bpy.context.active_object
    floor.name = "FLOOR"
    floor.scale = (width, depth, 1.0)
    floor.location = (width / 2, depth / 2, 0.0)
    floor.data.materials.append(materials["concrete"])

    # Walls are thin boxes rather than planes so they occlude from both sides and
    # cast the shadows a camera near a wall would actually see.
    thickness = 0.2
    walls = [
        ("WALL_S", (0.0, width), (-thickness, 0.0)),
        ("WALL_N", (0.0, width), (depth, depth + thickness)),
        ("WALL_W", (-thickness, 0.0), (0.0, depth)),
        ("WALL_E", (width, width + thickness), (0.0, depth)),
    ]
    for name, xs, ys in walls:
        add_box(name, xs, ys, height, materials["wall"])


def build_racking(config: dict[str, Any], materials: dict[str, BlenderObject]) -> None:
    """Build the eight racking blocks.

    These are the static occluders. The blind corridor behind RACK_2 is what makes
    the C02 occlusion case work, so their positions are not decorative.
    """
    racking = config["racking"]
    for block in racking["blocks"]:
        add_box(
            block["id"],
            tuple(block["x"]),
            tuple(block["y"]),
            racking["height"],
            materials["racking"],
        )


def build_zone_markings(config: dict[str, Any], materials: dict[str, BlenderObject]) -> None:
    """Paint the zone polygons onto the floor.

    Purely visual: zone membership is decided by the geometry primitives in
    packages/common against the same polygons in the config, never by pixels. The
    markings exist so a human reviewing a frame can see what the system is reasoning
    about.
    """
    for zone in config["zones"]:
        polygon = zone["polygon"]
        mesh = bpy.data.meshes.new(f"MARK_{zone['id']}")
        vertices = [(x, y, 0.003) for x, y in polygon]
        mesh.from_pydata(vertices, [], [list(range(len(vertices)))])
        mesh.update()
        obj = bpy.data.objects.new(f"MARK_{zone['id']}", mesh)
        obj.data.materials.append(materials["paint"])
        bpy.context.collection.objects.link(obj)


def aim_at(obj: BlenderObject, target: Vector) -> None:
    """Point an object's -Z axis at a world position.

    Blender cameras look down local -Z with +Y up. Computing the rotation directly
    avoids a Track To constraint, which would have to be resolved before any frame
    could be rendered and is one more thing to get wrong silently.
    """
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def build_cameras(config: dict[str, Any]) -> None:
    """Place the three cameras with the optics fixed in the spec."""
    optics = config["camera_optics"]
    for spec in config["cameras"]:
        camera_data = bpy.data.cameras.new(spec["id"])
        camera_data.sensor_width = optics["sensor_width_mm"]
        camera_data.lens = optics["focal_length_mm"]
        camera = bpy.data.objects.new(spec["id"], camera_data)
        camera.location = Vector(spec["location"])
        bpy.context.collection.objects.link(camera)
        aim_at(camera, Vector(spec["aim"]))


def build_lighting(config: dict[str, Any]) -> None:
    """Add flat overhead lighting.

    Constant across every case on purpose. Varying light between cases would make a
    detection failure ambiguous between "the model is weak here" and "this frame was
    darker", and the whole value of simulated data is that such ambiguity is
    avoidable.
    """
    house = config["warehouse"]
    width, depth = house["size_x"], house["size_y"]
    for index, (fx, fy) in enumerate([(0.25, 0.3), (0.75, 0.3), (0.25, 0.75), (0.75, 0.75)]):
        light_data = bpy.data.lights.new(f"HIGHBAY_{index}", type="AREA")
        light_data.energy = 900.0
        light_data.size = 6.0
        # 4000K neutral white, approximated in linear RGB.
        light_data.color = (1.0, 0.96, 0.90)
        light = bpy.data.objects.new(f"HIGHBAY_{index}", light_data)
        light.location = (width * fx, depth * fy, house["height_z"] - 0.4)
        bpy.context.collection.objects.link(light)


def configure_render(config: dict[str, Any]) -> None:
    """Set the render engine, resolution and frame rate from the config."""
    render_cfg = config["render"]
    scene = bpy.context.scene
    engine = render_cfg["engine"]
    try:
        scene.render.engine = engine
    except TypeError:
        # Engine identifiers moved between Blender 4.x and 5.x. Falling back is
        # better than failing the whole build over a rename.
        scene.render.engine = "BLENDER_EEVEE"
        log.info(f"! engine {engine!r} unavailable, fell back to {scene.render.engine!r}")

    optics = config["camera_optics"]
    scene.render.resolution_x = optics["resolution_x"]
    scene.render.resolution_y = optics["resolution_y"]
    scene.render.resolution_percentage = 100
    scene.render.fps = render_cfg["fps"]
    scene.frame_start = 1
    scene.frame_end = int(render_cfg["duration_s"] * render_cfg["fps"])

    # The object index pass is how ground truth is derived. Without it there are no
    # bounding boxes and no visibility fractions, only video.
    scene.view_layers[0].use_pass_object_index = True
    scene.view_layers[0].use_pass_z = True


def main() -> int:
    """Build the scene and save it."""
    args = script_args()
    config = json.loads(args.config.read_text())

    clear_scene()

    # Read from the config rather than hardcoded here. These were previously literals
    # in this file, which is why they were never checked against the entity colours
    # and why a forklift ended up 0.013 OKLab from the floor paint it stood on.
    surfaces = config["surfaces"]
    materials = {
        "concrete": make_material("CONCRETE", tuple(surfaces["concrete"]), roughness=0.9),
        "wall": make_material("WALL", tuple(surfaces["wall"]), roughness=0.85),
        "racking": make_material("RACKING", tuple(surfaces["racking"]), roughness=0.6),
        "paint": make_material("FLOOR_PAINT", tuple(surfaces["floor_paint"]), roughness=0.7),
    }

    build_shell(config, materials)
    build_racking(config, materials)
    build_zone_markings(config, materials)
    build_cameras(config)
    build_lighting(config)
    configure_render(config)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out))

    log.info(f"scene built: {args.out}")
    log.info(f"  objects  : {len(bpy.data.objects)}")
    log.info(f"  cameras  : {len([o for o in bpy.data.objects if o.type == 'CAMERA'])}")
    log.info(f"  frames   : {bpy.context.scene.frame_start}-{bpy.context.scene.frame_end}")
    log.info(f"  engine   : {bpy.context.scene.render.engine}")
    return 0


if __name__ == "__main__":
    # Blender runs its own bundled Python, so services.observability.logging is not
    # importable here. Same handler, spelled out rather than shared.
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    raise SystemExit(main())
