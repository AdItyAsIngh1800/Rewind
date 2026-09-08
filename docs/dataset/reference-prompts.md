# Dataset — Image generation prompts

Prompts for **Gemini 3.1 Pro (nano banana)**. Run these, then hand the images back to
Claude so they can be attached to the scene spec as build references.

These exist because a *look* is better generated than described. Nothing here defines
geometry — every coordinate, zone polygon and camera position is fixed in
[`scene-spec.md`](scene-spec.md) and must not be re-derived from an image. These are
**material, lighting and mood references for E1.1**, nothing more.

---

## P1 — Establishing reference (CAM_A viewpoint)

Purpose: match Blender materials and lighting for the main aisle view.

```json
{
  "task": "image_generation",
  "output": { "aspect_ratio": "16:9", "resolution": "1280x720", "count": 3 },
  "subject": "Interior of a modern industrial warehouse aisle, empty of people",
  "camera": {
    "placement": "ceiling-mounted security camera, 4.5 m above the floor, in a corner",
    "angle": "looking down and across at approximately 30 degrees below horizontal",
    "lens": "wide angle, roughly 70 degree horizontal field of view",
    "depth_of_field": "deep focus, everything sharp, as a fixed surveillance camera would be"
  },
  "scene": {
    "floor": "sealed polished concrete, light grey, with faded yellow painted lane markings running the length of the aisle and a hatched keep-clear square at an aisle intersection",
    "racking": "tall dark blue steel pallet racking on both sides, roughly 2.6 m high, loaded with shrink-wrapped pallets and cardboard boxes",
    "aisle": "a wide clear central aisle running away from camera toward a far wall",
    "ceiling": "exposed steel roof trusses with industrial LED high-bay light fixtures",
    "walls": "pale grey corrugated metal panel"
  },
  "lighting": {
    "type": "even overhead artificial LED lighting, no daylight",
    "temperature": "neutral white, approximately 4000K",
    "quality": "flat and diffuse with soft shadows directly under objects, no dramatic pools of light",
    "note": "deliberately uninteresting and consistent — this is a working facility, not a film set"
  },
  "style": {
    "render": "photorealistic, as if a still frame from a fixed CCTV camera",
    "grade": "slightly desaturated, mild sensor noise, no colour grading or stylisation",
    "avoid": "lens flare, god rays, cinematic teal-orange grade, dramatic contrast, motion blur, people, text overlays, timestamp burn-in, watermarks, fisheye distortion"
  },
  "negative_prompt": "people, faces, humans, workers, warped geometry, tilted horizon, HDR halos, oversaturated colours, artistic composition, shallow depth of field, bokeh"
}
```

## P2 — Overhead intersection reference (CAM_C viewpoint)

Purpose: the intersection is where every incident resolves. This is the view the
occlusion case depends on.

```json
{
  "task": "image_generation",
  "output": { "aspect_ratio": "16:9", "resolution": "1280x720", "count": 3 },
  "subject": "Overhead view of a warehouse aisle intersection, empty of people",
  "camera": {
    "placement": "ceiling-mounted, 5 m above the floor, directly north of the intersection",
    "angle": "steep downward angle, approximately 55 degrees below horizontal, near top-down",
    "lens": "wide angle, roughly 70 degree horizontal field of view"
  },
  "scene": {
    "floor": "polished concrete with a clearly painted yellow hatched keep-clear square approximately 4 m by 4 m at the crossing of two aisles, plus solid yellow lane edge lines",
    "surroundings": "the ends of four dark blue steel racking blocks framing the four corners of the intersection",
    "detail": "faint tyre scuffs and scratches on the concrete, a floor drain, a wall-mounted safety mirror on a post at one corner"
  },
  "lighting": {
    "type": "even overhead LED high-bay",
    "temperature": "neutral white, approximately 4000K",
    "quality": "flat, diffuse, minimal shadow"
  },
  "style": {
    "render": "photorealistic fixed-camera CCTV still",
    "grade": "desaturated, mild noise, flat contrast",
    "avoid": "people, vehicles, dramatic lighting, stylisation, text, watermarks"
  },
  "negative_prompt": "people, forklifts, vehicles, boxes in the aisle, cinematic grade, lens flare, fisheye, text, timestamp"
}
```

## P3 — Entity reference sheet

Purpose: asset selection and material matching for the four entity classes. Generated
as a flat reference sheet rather than a scene, so proportions can be read directly.

```json
{
  "task": "image_generation",
  "output": { "aspect_ratio": "16:9", "resolution": "1600x900", "count": 2 },
  "subject": "Technical reference sheet showing four warehouse objects side by side on a plain neutral grey background",
  "layout": "four objects evenly spaced in a single row, each fully visible, three-quarter view, consistent scale relative to one another, a subtle ground shadow under each",
  "objects": [
    {
      "name": "worker",
      "description": "a generic featureless mannequin figure approximately 1.75 m tall wearing a high-visibility safety vest over dark work clothes and a hard hat",
      "note": "no facial features, no identifiable person, mannequin-like and anonymous"
    },
    {
      "name": "autonomous mobile robot",
      "description": "a low rectangular white and dark grey autonomous warehouse robot approximately 1.2 m tall, flat top deck, small wheels, a green status light strip along one side"
    },
    {
      "name": "forklift",
      "description": "a compact counterbalance warehouse forklift approximately 2.2 m tall to the top of its mast, yellow and black, forks lowered, no driver"
    },
    {
      "name": "pallet",
      "description": "a standard wooden shipping pallet 1.2 m by 1.0 m, empty, viewed at a slight angle"
    }
  ],
  "lighting": {
    "type": "even neutral studio lighting, no strong direction",
    "quality": "soft and shadowless apart from a light contact shadow"
  },
  "style": {
    "render": "clean product-photography realism on a flat neutral background",
    "avoid": "human faces, identifiable people, branding, logos, text labels, dramatic lighting, background scenery"
  },
  "negative_prompt": "faces, identifiable humans, brand logos, text, labels, watermarks, cluttered background, dramatic shadows"
}
```

---

## Notes on use

- **P1 and P2 set materials and lighting only.** Camera positions come from
  `scene-spec.md` §4 and are not negotiable — a generated image that looks better from
  a different angle is not a reason to move a camera.
- **P3 informs asset selection.** The preference is still to source CC0 assets rather
  than model anything by hand (risk R18). Use the sheet to judge whether a candidate
  asset has the right proportions and read.
- **Deliberately anonymous figures.** The person prompt asks for a featureless
  mannequin. Face recognition is a permanent non-goal, and the dataset should not
  contain identifiable faces even synthetic ones.
- Generate 2–3 variants of each and keep the one closest to *boring*. A dramatic
  reference produces a dramatic scene, and dramatic lighting makes detection results
  unrepresentative.
