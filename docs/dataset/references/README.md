# Dataset — Visual reference assessment

Generated 2026-09-09 with Gemini 3.1 Pro from the prompts in
[`reference-prompts.md`](reference-prompts.md). Assessed against
[`scene-spec.md`](scene-spec.md) before use.

**These are material and lighting references only.** Where a reference disagrees with
the scene spec, **the spec wins** — every coordinate, camera position and dimension is
fixed there. A generated image that looks better from a different angle is not a reason
to move a camera.

---

## P1 — Establishing aisle · `P1-establishing-aisle.png`

**Adopt.** The single most useful reference of the three for surfacing.

| Take from it | Why |
|---|---|
| Sealed concrete floor, mid-grey, with tyre scuffs and drag marks | Exactly the "working facility, not a film set" read the spec asks for. Scuffs also give the floor texture variation, which matters — a perfectly uniform floor makes shadow and contact-point estimation unrealistically easy |
| Blue uprights, orange beams, yellow base guards | Strong colour separation from grey floor and brown goods. Helpful for detection, and it is the real-world convention |
| Solid yellow lane edge lines | The lane marking language for `Z1` |
| Pale corrugated metal end wall | Cheap to model, correct read |

### Do not copy

- **Skylights and daylight.** The roof has translucent panels. Scene spec §8 fixes
  lighting as constant overhead LED across all six cases *specifically so that a
  detection failure is attributable to the scene rather than to the light*. Daylight
  would vary by case and destroy that property. Overhead LED only.
- **Rack height.** These racks read as roughly 6 m. The spec fixes them at **2.6 m**,
  deliberately: tall enough to occlude a person from a wall-mounted camera, short
  enough that the ceiling-mounted `CAM_C` still sees over them. At 6 m the scene has no
  usable overhead view and the occlusion cases stop being controllable.
- **Aisle proportions.** The spec's aisles are 4 m wide against 2.6 m racking. That is
  a wider, lower space than this image.

## P2 — Intersection · `P2-intersection-variants.png`

**Adopt the floor markings. Discard the camera.** The generator returned four variants
in one grid rather than three images; that is fine.

| Take from it | Why |
|---|---|
| Yellow diagonal hatch keep-clear square | Precisely the marking language for `Z2`. This is the reference's main contribution |
| Floor drain centred in the hatch | Free authenticity, and a small fixed floor feature is a useful visual landmark when checking camera alignment |
| Convex safety mirror on a corner post | Requested and delivered |
| Racking end-caps framing the crossing | Correct structure for the four corners of `Z2` |

### Do not copy

- **Fisheye distortion.** Heavy barrel distortion — ceiling lines visibly curve. This
  was explicitly excluded in the prompt and appeared anyway. Scene spec §4 fixes all
  three cameras as **rectilinear, 70° horizontal FOV, 25.7 mm on a 36 mm sensor**.
  Introducing barrel distortion would require undistortion before any geometry work and
  would corrupt world-coordinate ground truth for no benefit.
- **Camera height and angle.** These read as roughly eye level. `CAM_C` sits at
  **5.0 m aiming down at about 55°**. This image is not a `CAM_C` preview.
- **Single aisle.** The spec's `Z2` is a genuine four-way crossing of two 4 m aisles.
  These images show one aisle with a hatched patch in it.

## P3 — Entity sheet · `P3-entity-sheet.png`

**Adopt almost wholesale.** The strongest of the three, and it matches the spec's
dimensions without needing correction.

| Entity | Spec | Reference | Verdict |
|---|---|---|---|
| `person` | 1.75 m, hi-vis vest | 1.75 m, hi-vis over dark workwear, hard hat, **featureless mannequin head** | Correct, including the anonymity requirement |
| `robot` | 1.2 m AMR | 1.2 m, white and grey, green status strip | Correct. The status strip is a useful bonus: it gives the `MOVING` / `ESTOP` / `IDLE` state channel a visible correlate for demo video |
| `forklift` | 2.2 m, mobile occluder | 2.2 m, yellow and black, no driver | Correct |
| `pallet` | 1.2 x 1.0 m | 1.2 x 1.0 m, standard stringer pallet | Correct |

The dimension annotations were not requested and are genuinely useful — they make the
sheet usable directly as a modelling reference.

### One correction needed

There is a **generator watermark in the lower right**. It was negative-prompted and
appeared regardless. Crop it before this image is used in the final report or
presentation. Harmless as an internal build reference.

---

## Open issue surfaced by these references

Both warehouse references show racking **loaded with hundreds of shrink-wrapped
pallets**. `pallet` is one of the four tracked entity classes. If stored pallets are
visible in racking, a detector will fire on all of them while ground truth labels only
the one on the floor — producing an apparent false-positive rate that reflects an
annotation ambiguity rather than a detector fault.

This is a scene-authoring decision, not a modelling one, and it is tracked in
`scene-spec.md` §10 open items rather than resolved here.
