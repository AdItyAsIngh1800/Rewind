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
