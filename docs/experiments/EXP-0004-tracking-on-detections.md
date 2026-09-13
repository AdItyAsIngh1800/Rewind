# EXP-0004: ByteTrack on real detections

- **Date:** 2026-09-11
- **Status:** Complete

| Field | Value |
|---|---|
| Hypothesis | With `yolo11n-rewind-v1` boxes instead of exact ones, ByteTrack at `match_thresh=0.90` stays within the charter floor of 2 id switches per camera per case |
| Dataset version | `v1`, the four tune cases (`case_01/03/04/05`), 12 camera-cases; golden cases sealed |
| Preprocessing | `process_camera` end to end: decode at 10 FPS, detect, track. Tracked boxes assigned a true `entity_id` by IoU ≥ 0.5 within frame and class, then scored with `score_against_truth` |
| Model / tracker version | `yolo11n-rewind-v1:native:conf0.25`, `bytetrack:buf30:match0.9:fps10` |
| Hyperparameters | Swept detector NMS IoU ∈ {0.7, 0.6, 0.5, 0.4}; tracker unchanged from EXP-0002 |
| Hardware | Apple M4, MPS |
| Config version | `v0.1.0` |

## Metrics

| NMS IoU | Id switches (12 camera-cases) | Worst camera | Spurious boxes | Tracked boxes |
|---|---|---|---|---|
| 0.7 (Ultralytics default) | 7 | 4 | 300 | 7739 |
| 0.6 | 8 | 5 | 111 | 7549 |
| **0.5** | **2** | **1** | **59** | 7497 |
| 0.4 | 1 | 1 | 50 | 7483 |

"Spurious" is a tracked box overlapping no ground-truth box of its class at IoU 0.5.

Against EXP-0002 on the same four cases with perfect boxes: 4 switches. Real
detections at NMS 0.5 give 2. The tracker is not the bottleneck.

## Failure cases

| Camera-case | What | Cause |
|---|---|---|
| `case_03 CAM_A` at NMS 0.7 | 4 switches on P02, 222 spurious boxes | Duplicate detection of a partially occluded person (EXP-0003). Which duplicate matched the visible-box ground truth flipped frame to frame, so the *scoring* saw switches while track `T001` actually held P02 throughout. Removed by NMS 0.5. |
| `case_01 CAM_A` P01 | 1 switch, 2 tracks | The 7.9 s walkway crossing already catalogued in EXP-0002: a re-acquisition after a long gap, which no box-only tracker bridges. |
| `case_03 CAM_B` P02 | 1 switch, 2 tracks, 25 spurious | P02 partly behind P01 again from the second view; one short phantom track during the overlap. |

## Result

The one degradation real detections introduced was a detector artefact, not a tracking
one, and the fix belongs in the detector: NMS at 0.7 is tuned for COCO's crowded scenes,
where two people at IoU 0.65 are usually two people. In this scene they were one person
detected twice. 0.4 gains one switch over 0.5 but would begin suppressing two people who
genuinely overlap, which `case_03` shows is common from an elevated camera.

## Decision

**Adopt NMS IoU 0.5** as `DetectorConfig.iou`. The value is now part of the detector
version string so a run records it. Tracker settings from EXP-0002 stand.

Gate 1 criterion "id-switch rate usable for E5" is met: 2 switches in 12 camera-cases,
none above the floor, both of the remaining ones the long-gap kind that E5's appearance
features exist to bridge.

## Next experiment

`EXP-0005`, in E5: colour-histogram appearance baseline for cross-camera association.

## Re-run, 2026-09-13 — retrained checkpoint, and an edge rule

The checkpoint retrained on the per-actor colour render (EXP-0003 re-run) regressed
tracking from 2 switches to **5, with 4 on `case_03 CAM_B` P02** — above the floor.

Traced per track: P02 enters CAM_B from the bottom edge at frame 133. The detector
reported it as a 4 px sliver (frames 136–140, track T003), then 13 px (141–146,
T005), then the real 44 px box (144–279, T007), and another sliver on exit (268–276,
T008). The box height tripled between frames, so each growth step fell below
`match_thresh` and opened a new track. The main track never switched. The old
checkpoint happened to emit fewer slivers; nothing about the tracker changed.

Swept dropping detections that touch the frame border with a shorter side under N px:

| Edge rule | Id switches | Worst camera | Spurious | Detections dropped |
|---|---|---|---|---|
| none | 5 | 4 (`case_03 CAM_B`) | 44 | 0 |
| < 12 px | 2 | 1 | 32 | 25 |
| **< 16 px** | **1** | **1** (`case_01 CAM_A`) | **26** | **39** |
| < 24 px | 1 | 1 | 22 | 60 |

Edge-only, because interior people at range are 13.8 px wide in the ground truth and
a global size floor would drop them. Such a sliver is not usable evidence anyway: its
centre is not the entity's, so it would back-project to the wrong floor position.

Through the full pipeline with the rule (`tracking-on-detections-2026-09-13T112059Z`):
`case_03 CAM_B` 0 switches, 3 tracks for 3 entities, 1 spurious box (was 25 on the
first render). Detection precision and recall on `case_05` and `case_04` are
unchanged to the box.

**Decision: adopt `DetectorConfig.edge_min_side_px = 16`**, the smallest value on the
plateau; recorded in the detector version string (`:edge16`). The one remaining switch
is the long-gap re-acquisition on `case_01 CAM_A` P01.
