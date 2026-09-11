# EXP-0006: Semantic events from the real pipeline

- **Date:** 2026-09-11
- **Status:** Complete

| Field | Value |
|---|---|
| Hypothesis | Events extracted from `yolo11n-rewind-v1` + ByteTrack + camera back-projection reach the perfect-track ceiling of EXP-0005 on the tune cases; where they do not, the cause is localisation, not tracking |
| Dataset version | `v1`, the four tune cases; golden pair sealed |
| Preprocessing | `process_camera` end to end per clip (decode at 10 FPS, detect at NMS 0.5, track at `match_thresh` 0.9), then `extract_events` and `merge_across_cameras`. Exactly what a worker run persists |
| Model / tracker version | `yolo11n-rewind-v1:native:conf0.25:iou0.5`, `bytetrack:buf30:match0.9:fps10`, `events:stop0.1/1.0:turn60.0/0.5:prox1.5:occ0.5:merge1.0` |
| Hyperparameters | Swept `merge_tolerance_s` ∈ {0.5, 0.8, 1.0, 1.5}; merged timestamp changed from first sighting to median camera time |
| Hardware | Apple M4, MPS |
| Config version | `v0.1.0` |

## Metrics

Totals over the four tune cases, zone entry/exit, observable truth only (EXP-0005
defines observable and bounded).

| Merge window | Positions | TP | FP | FN | P | R | Max timing |
|---|---|---|---|---|---|---|---|
| 0.5 s | projected perfect tracks | 23 | 4 | 2 | 0.85 | 0.92 | 0.2 s |
| 0.5 s | **real detections** | 23 | 19 | 2 | 0.55 | 0.92 | 0.4 s |
| 1.0 s | projected perfect tracks | 23 | 3 | 2 | 0.88 | 0.92 | 0.2 s |
| **1.0 s** | **real detections** | 23 | 3 | 2 | **0.88** | **0.92** | **0.4 s** |
| 1.5 s | real detections | 23 | 3 | 2 | 0.88 | 0.92 | 0.4 s |

Per case at 1.0 s on real detections:

| Case | TP | FP | FN | P | R | Max timing |
|---|---|---|---|---|---|---|
| case_01 | 7 | 1 | 0 | 0.88 | 1.00 | 0.4 s |
| case_03 | 7 | 0 | 0 | 1.00 | 1.00 | 0.4 s |
| case_04 | 6 | 2 | 2 | 0.75 | 0.75 | 0.0 s |
| case_05 | 3 | 0 | 0 | 1.00 | 1.00 | 0.4 s |

## Failure cases

| Case | What | Cause |
|---|---|---|
| all, merge 0.5 s | 19 false positives, every one a crossing that truth also has | Three cameras time one crossing up to 0.7 s apart (case_04 Z1 entry: CAM_B 11.8, CAM_A 12.2, CAM_C 12.5, truth 12.2) because each camera's single-point localisation is biased in its own direction. A 0.5 s window split one crossing into two events. Not a tracking error: per-camera track ids were stable through every crossing |
| case_04 | F01 Z5 entry/exit from CAM_C early and late | Forklift box-centre bias from the steep camera, as in EXP-0005. Unchanged by the real detector |
| case_01 | P01 exits Z3 at 1.2 s in CAM_A (truth 7.2 s, occluded) | P01 is 38% visible behind racking at 16 m; the box is the visible fragment, so its centre back-projects a metre off. The extractor is honest about what it was given: the exit is emitted at full confidence because the track was continuous. A visibility-aware confidence is the natural fix and needs the detector to report partial visibility, which it does not |

## Result

The merge window, not perception, was the Gate 2 blocker. At 1.0 s the real
pipeline is indistinguishable from perfect tracks with projected positions on these
cases, and the residual errors are the two localisation limits already documented.
The median camera time is what keeps the timing error at 0.4 s despite per-camera
biases of up to 0.5 s.

## Decision

**Adopt `merge_tolerance_s = 1.0` and median timestamps.** The naive merge's known
weakness, two same-class entities crossing one zone within a second from different
cameras, is now a one-second weakness rather than a half-second one; that is
acceptable because E5 replaces the rule with identity links.

## Next experiment

E5.2: colour-histogram appearance baseline for cross-camera association, which also
enables averaging positions across cameras and retiring both residual failure modes.

## Correction, 2026-09-12

The E5.1 clock check found that the configured camera offsets (`CAM_B` +0.4 s,
`CAM_C` -0.2 s) were never baked into the clips, so applying them at ingestion had
shifted CAM_B 0.4 s early and CAM_C 0.2 s late in every "real detections" row above.
The 0.7 s camera spread in the failure table is that error, not localisation. The
offsets are now zero (scene spec §4.1, amended) and the sweep was repeated:

| Merge window | TP | FP | FN | P | R | Max timing |
|---|---|---|---|---|---|---|
| 0.3 s | 23 | 8 | 2 | 0.74 | 0.92 | 0.1 s |
| 0.5 s | 23 | 4 | 2 | 0.85 | 0.92 | 0.2 s |
| **0.8 s** | 23 | 3 | 2 | **0.88** | **0.92** | **0.2 s** |
| 1.0 s | 23 | 3 | 2 | 0.88 | 0.92 | 0.2 s |

Same precision and recall as before, timing error halved to 0.2 s, and the genuine
cross-camera spread is under 0.5 s. **Decision amended: `merge_tolerance_s = 0.8`**,
the smallest window that covers the real spread. The residual three false positives
and two misses are unchanged and remain the two localisation limits.
