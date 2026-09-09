# Dataset — Scene Specification

- **Version:** v1 (frozen for dataset `v1`)
- **Date:** 2026-09-09
- **Consumed by:** E1.1 (scene build), E1.2 (rendering + ground truth), E1.3 (manifest)

This document is written **before** anything is rendered. E1.1 should be transcription,
not invention. If a value here turns out to be wrong, change it here first, bump the
dataset version, and log a deviation-ledger row.

---

## 1. Why simulated

Three properties that public footage cannot give us, each load-bearing:

1. **Frame-exact ground truth** for every entity in every camera, for free. The
   evaluation harness compares like with like because ground truth is exported in the
   same `Observation` schema the detector produces.
2. **Repeatable incidents.** The same incident can be re-rendered with a camera moved,
   an occluder added, or an actor's timing shifted by 200 ms. That makes failure
   analysis an experiment rather than an anecdote.
3. **No privacy or licensing surface at all.** No real people, no consent questions, no
   dataset licence to audit.

The cost is realism, and it is a real cost. Stretch item 1 (a public-footage check on
WILDTRACK or MMPTRACK) exists specifically to measure how much it cost.

## 2. Coordinate system and units

- Right-handed, **Z up**, matching Blender's world axes.
- Origin at the **south-west floor corner** of the warehouse interior.
- Units are **metres**. All zone polygons, camera positions and actor waypoints below
  are in world metres and are copied verbatim into the Blender scene.
- Time is seconds from the start of the case clip. Wall-clock timestamps are assigned
  at ingestion by adding the case `t0` from the manifest.

## 3. Warehouse geometry

Interior **24 m (X) x 16 m (Y) x 6 m (Z)**.

```
Y
16 +----------------------------------------------------------+
   |  PEDESTRIAN WALKWAY  (Z3)                                |
14 +----------------------------------------------------------+
   |          |              |  CAM_C  |            |         |
   |  RACK 1  |    RACK 2    |         |   RACK 3   | RACK 4  |
12 |          |              |         |            |         |
   |          |              |         |            |         |
10 +----------+--------------+---------+------------+---------+
   |                                                          |
 8 |  <<<<<<<<<<<<  ROBOT LANE  (Z1)  >>>>>>>>>>>>>>>>>>>>>>  |   CAM_B
   |                    [ INTERSECTION Z2 ]                   |    (east,
 6 +----------+--------------+---------+------------+---------+   looking W)
   |          |              |         |            |         |
   |  RACK 5  |    RACK 6    |  CROSS  |   RACK 7   | RACK 8  |
 4 |          |              |  AISLE  |            |         |
   +----------+              |         |            |         |
   | LOADING  |              |         |            |         |
 2 | BAY (Z4) |              |         |            |         |
   |          |              |         |            |         |
 0 +----------------------------------------------------------+
   0     4        8      10     12    14      18       22     24  X
        ^CAM_A (north-west, looking south-east)
```

### 3.1 Racking blocks (static occluders)

Solid boxes, **2.6 m tall** — above eye level, so they occlude cameras but not the
ceiling-mounted views entirely. This is what creates natural blind spots.

**Racking stays densely loaded.** The occlusion cases depend on it: `C02` needs the
blind corridor behind RACK 2 to be genuinely blind. Sparse racking would weaken the
project's central claim.

**But stored goods must never show a visible pallet.** Load the racking with boxed
units, shrink-wrapped stacks and closed containers whose base is hidden. `pallet` is a
tracked entity class, so a visible pallet in racking would be detected while ground
truth labelled only the floor-level one — an apparent false-positive rate that is
really an annotation ambiguity. Fixing it at the source in the scene is cleaner than
explaining it away in every benchmark report afterwards.

| Rack | X range | Y range |
|---|---|---|
| RACK 1 | 0.5 – 4.5 | 10.5 – 13.5 |
| RACK 2 | 6.0 – 9.5 | 10.5 – 13.5 |
| RACK 3 | 14.5 – 18.0 | 10.5 – 13.5 |
| RACK 4 | 19.5 – 23.5 | 10.5 – 13.5 |
| RACK 5 | 0.5 – 4.5 | 2.5 – 5.5 |
| RACK 6 | 6.0 – 9.5 | 1.0 – 5.5 |
| RACK 7 | 14.5 – 18.0 | 1.0 – 5.5 |
| RACK 8 | 19.5 – 23.5 | 1.0 – 5.5 |

### 3.2 Zones

Zone polygons are the input to the E4.1 geometry primitives. They are stored as
world-space polygons in `ml/configs/zones_v1.yaml` and are **not** camera-specific.

| ID | Name | Polygon (X,Y) | Purpose |
|---|---|---|---|
| `Z1` | `ROBOT_LANE` | (2,6.5) (22,6.5) (22,9.5) (2,9.5) | The robot's travel corridor. A person inside it is the flagship trigger condition. |
| `Z2` | `INTERSECTION_KEEPCLEAR` | (10,6) (14,6) (14,10) (10,10) | Must stay clear. Dwell beyond threshold is incident class 2. |
| `Z3` | `PEDESTRIAN_WALKWAY` | (0,14) (24,14) (24,16) (0,16) | Where people are supposed to be. Exiting it toward Z1 is the precursor event. |
| `Z4` | `LOADING_BAY` | (0,0) (6,0) (6,4) (0,4) | Forklift origin and pallet source. |
| `Z5` | `CROSS_AISLE` | (10,0) (14,0) (14,6) (10,6) | North-south forklift route feeding the intersection. |

## 4. Cameras

All three: **1280 x 720, 10 FPS**, sensor width 36 mm, focal length **25.7 mm**
(≈ 70° horizontal field of view). Fixed, no motion, no auto-exposure.

| ID | Position (X,Y,Z) | Aim point | Sees | Deliberately cannot see |
|---|---|---|---|---|
| `CAM_A` | (4.0, 14.0, 4.5) | (12.0, 8.0, 0.0) | West half of Z1, the walkway exit, west approach to the intersection | Ground behind RACK 2 (X 6–9.5, Y ≈ 10.5) — the **blind corridor** |
| `CAM_B` | (23.0, 8.0, 4.0) | (6.0, 8.0, 0.8) | Full length of Z1 from the east, at a shallow angle | Anything north of the racks; heavily foreshortened past X ≈ 8 |
| `CAM_C` | (12.0, 13.5, 5.0) | (12.0, 7.0, 0.0) | The intersection Z2 from above, both aisle approaches | Occluded by any object taller than 1.8 m standing at (13, 11) |

**Overlap is intentional and unequal.** Z2 is covered by all three; the west end of Z1
by A and B only; the blind corridor behind RACK 2 by none. Cross-camera identity is
only interesting because coverage is uneven.

### 4.1 Camera timing offsets

Cameras are rendered frame-synchronous, then **deliberately desynchronised at
manifest time** by a per-camera offset, so that E5.1 has something real to correct:

| Camera | Offset written into the manifest |
|---|---|
| `CAM_A` | `+0.0 s` (reference clock) |
| `CAM_B` | `+0.4 s` |
| `CAM_C` | `-0.2 s` |

The ground truth is stored on the **true** clock. A pipeline that ignores the offsets
will produce visibly wrong event ordering, and the E5.1 synchronization test asserts
exactly that.

## 5. Entities

| Class | Height | Speed | Notes |
|---|---|---|---|
| `person` | 1.75 m | 1.2–1.5 m/s walking | High-visibility vest; distinct vest colour per actor so appearance features have signal |
| `robot` | 1.2 m | 1.0 m/s | AMR-style box on wheels. Carries a state channel: `MOVING` / `ESTOP` / `IDLE` |
| `forklift` | 2.2 m | 2.0 m/s | Tall enough to occlude `CAM_C`. The scene's mobile occluder |
| `pallet` | 0.15 m (1.2 x 1.0 m footprint) | static | Carried by the forklift or left on the floor. **A `pallet` entity is floor-level only** — stored goods in racking are scenery, not entities |

The robot's `ESTOP` state is exported in the ground truth as a state-change event. It
is the **trigger**, not something to be inferred from motion — the incident detector
reads a state channel, exactly as it would from a real robot's telemetry.

## 6. The six cases

45 s per case at 10 FPS = **450 frames per camera, 1350 frames per case**.

| ID | Name | Class | Split | What it exercises |
|---|---|---|---|---|
| `C01` | `ESTOP_CLEAN` | 1 | tune | The happy path. All three cameras see the incursion. Baseline for everything. |
| `C02` | `ESTOP_OCCLUDED` | 1 | **golden** | The critical interval is invisible to every camera. Must produce `UNKNOWN`. |
| `C03` | `ESTOP_CROSSCAM` | 1 | tune | Person crosses the blind corridor; identity must survive a gap between CAM_A and CAM_B. |
| `C04` | `BLOCKED_ZONE` | 2 | tune | Pallet left in Z2 past the dwell threshold. Single-entity trigger. |
| `C05` | `NEAR_MISS` | none | tune | Person approaches Z1 and stops short. Robot does **not** stop. **Negative case.** |
| `C06` | `BLOCKED_AMBIGUOUS` | 2 | **golden** | Two plausible causes for the obstruction. Tests hypothesis *ranking*, not detection. |

> `C05` carries more weight than its position suggests. Without a negative case the
> false-alert rate is unmeasurable, and an incident detector that fires on everything
> scores perfectly on five cases out of six.

### 6.1 `C01 ESTOP_CLEAN` — actor script

| t (s) | Entity | Action |
|---|---|---|
| 0.0 | `robot_R12` | Enters Z1 at (2.0, 8.0), heading east at 1.0 m/s, state `MOVING` |
| 0.0 | `person_P01` | Walking west along Z3 at (18.0, 15.0), 1.3 m/s |
| 6.0 | `person_P01` | Turns south at (12.0, 15.0), leaves Z3 toward the cross aisle |
| 11.5 | `person_P01` | **Enters Z2** at (12.0, 10.0) — first material event |
| 12.8 | `person_P01` | **Enters Z1** at (12.0, 9.5) |
| 13.0 | `robot_R12` | At (13.2, 8.0). Separation to P01 is 1.6 m and closing |
| 13.4 | `robot_R12` | **State changes to `ESTOP`** — the incident trigger |
| 14.0 | `person_P01` | Stops at (12.0, 8.6), notices the robot |
| 18.0 | `person_P01` | Retreats north, exits Z1 |
| 24.0 | `robot_R12` | State returns to `IDLE` |
| 45.0 | — | Clip ends |

**Expected reconstruction.** Contributing cause ranked first: *person P01 entering Z1
at 12.8 s while robot R12 was approaching*. Supporting evidence: the Z3 exit, the Z2
entry, the Z1 entry, the converging separation, and the state change 0.6 s later. This
is the case the whole system is tuned against.

### 6.2 `C02 ESTOP_OCCLUDED` — the UNKNOWN case

Identical to `C01`, with two changes:

- A `forklift_F01` is parked at **(13.0, 11.0)** from t = 8.0 s, oriented north-south.
  Being 2.2 m tall, it occludes `CAM_C`'s view of the intersection floor.
- `person_P01` approaches through the **blind corridor** behind RACK 2 instead of the
  cross aisle, entering Z1 at (8.5, 9.5) at t = 12.9 s — a point `CAM_A` cannot see
  past the rack and `CAM_B` sees only as a few foreshortened pixels.

**Required output.** The robot's `ESTOP` at 13.4 s is `CONFIRMED` (state channel).
P01's presence before 11 s and after 16 s is `CONFIRMED`. The interval **11.0–16.0 s is
an evidence gap** and the system must report *cannot determine* whether P01 entered
Z1 — while still ranking "person entered the lane" as a `POSSIBLE` hypothesis, because
it is consistent with the surrounding evidence.

**A build that confidently reports an incursion here has failed.** So has one that
reports nothing at all — the gap must be *named*, not silently skipped.

### 6.3 `C03 ESTOP_CROSSCAM`

P01 is visible to `CAM_A` in the west, disappears into the blind corridor for ~4 s,
and reappears in `CAM_B`'s view in the east. A second person `P02` in a different vest
colour is present in `CAM_B` throughout, as a **distractor**. The identity layer must
link P01's two segments and must *not* link P01 to P02.

The false-link here is the expensive failure: linking P01 to P02 fabricates a
trajectory that never happened, and every downstream conclusion inherits it.

### 6.4 `C04 BLOCKED_ZONE`

`forklift_F01` carries `pallet_PL3` from Z4, drops it at (12.0, 8.0) — inside Z2 — at
t = 14 s, and leaves. The pallet dwells past the 20 s threshold. Trigger fires at
t = 34 s. Straightforward; this is the fallback that satisfies the Definition of Done
if class 1 reconstruction proves too hard.

### 6.5 `C05 NEAR_MISS` — negative case

P01 walks from Z3 toward Z1 and **stops at (12.0, 10.2)**, inside Z2 but never
entering Z1. Robot R12 passes through at 1.0 m/s without changing state. Minimum
separation 2.1 m.

**Expected output: no incident.** A zone-entry event for Z2 and a proximity event are
both correctly generated — the incident *trigger* must not fire on them.

### 6.6 `C06 BLOCKED_AMBIGUOUS` — ranking under ambiguity

`forklift_F01` drops `pallet_PL3` near the Z2 boundary at t = 10 s. At t = 22 s
`forklift_F02` passes through and nudges it fully inside Z2. The obstruction trigger
fires at t = 42 s.

Two defensible hypotheses: F01 placed it, or F02 moved it in. Both have real support.
**The system must surface both with scores, not pick one and hide the other.** The
annotated ground-truth cause is F02, but a system that ranks F01 first with F02 a close
second is behaving correctly; one that reports a single cause is not.

## 7. Ground-truth export

Ground truth is written in **the same `Observation` schema the detector emits** — this
is what makes the evaluation harness trivial rather than a translation layer.

Per case, per camera, per frame, for every visible entity:

```
observation_id, run_id="GT", camera_id, frame_index, timestamp_s,
class, entity_id, bbox_xyxy, world_xyz, visibility, confidence=1.0
```

`visibility` is the fraction of the entity's silhouette not occluded, computed inside
the Blender render loop from the object-index and depth passes **without persisting
them** (see §8).

**Floor-level filter for pallets.** A `pallet` observation is emitted only when
`world_z < 0.5`. This is a safety net, not the primary fix — the primary fix is that
racking contains no visible pallets at all (§3.1). If this filter ever discards
anything, the scene is wrong and should be corrected rather than relied on to
compensate. **`visibility < 0.15` means the entity
is not emitted at all** — ground truth must not claim to see what a camera cannot,
otherwise the occlusion cases score as detector failures rather than as the evidence
gaps they are.

Alongside the per-frame observations, each case exports:

- `events_gt.json` — the annotated semantic-event timeline (the table in §6.1 above).
- `identities_gt.json` — true cross-camera identity mapping.
- `cause_gt.json` — the annotated contributing cause, for cause-ranking evaluation.
- `gaps_gt.json` — intervals where no camera has visibility of a named entity. **This
  is the ground truth for the uncertainty engine**, and without it `C02` cannot be
  scored at all.

## 8. Render settings

| Setting | Value | Why |
|---|---|---|
| Engine | **EEVEE Next** | Real-time raster. Cycles' path tracing buys realism the detector does not need and costs hours per case. |
| Resolution | 1280 x 720 | Matches the documented operating envelope. |
| Frame rate | 10 FPS | Enough temporal resolution for 1.5 m/s motion; a quarter of the frames of 40 FPS. |
| Duration | 45 s (450 frames) | Long enough for a 20 s dwell threshold plus a rewind window either side. |
| Output | H.264 MP4 only. Object-index and depth passes are **consumed in-process and never written to disk** | Persisting 8,100 frames of passes would cost roughly 10 GB against 32 GB free. Bounding boxes and visibility are computed inside the render loop and emitted straight to JSON. |
| Lighting | Fixed overhead area lights, no variation between cases | Lighting variation is not a variable under study; keeping it constant means detector failures are attributable. |

Total render: 6 cases x 3 cameras x 450 frames = **8,100 frames**.

## 9. Visual reference

The Blender scene needs a look to build against. Precise geometry comes from the tables
above; the *material and lighting* reference is better generated than described.

See `docs/dataset/reference-prompts.md` for the image-generation prompt.

## 10. Open items

Tracked here rather than discovered during E1.1:

- [ ] Source CC0 warehouse assets (racking, pallets, forklift). **Do not model by hand**
      — R18 in the risk register exists for this.
- [ ] Confirm EEVEE Next renders the object-index pass needed for ground-truth bboxes.
- [ ] Decide whether the robot is a purchased asset or a primitive box. A box is
      probably fine and is one less thing to fail. *(The P3 reference suggests a
      simple box with a coloured status strip is enough, and the strip gives the
      robot state channel a visible correlate.)*
- [x] **Stored-pallet ambiguity — resolved.** Racking stays dense but carries no
      visible pallets (§3.1), with a `world_z < 0.5` filter as a safety net (§7).
- [x] **Detector class coverage — resolved.** COCO covers `person` only; `yolo11n` is
      fine-tuned on the four tuning cases. See `ADR-0004`.
- [ ] **Verify no pallet edges are visible.** After the scene is built, render a
      handful of frames from all three cameras and inspect the racking directly. A
      pallet edge peeking from under a shrink-wrapped stack silently contaminates
      every precision measurement that follows, and it is far cheaper to catch here
      than to explain in the Gate 1 report.
- [ ] **Assert split integrity.** The training split manifest must be checked by
      asserting on case IDs — no `C02` or `C06` frame may appear in any training or
      validation split.
