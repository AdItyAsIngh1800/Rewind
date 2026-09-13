# EXP-0008: Incident triggers and rewind windows

- **Date:** 2026-09-13
- **Status:** Complete

| Field | Value |
|---|---|
| Hypothesis | Two deterministic rules over the merged event stream (robot telemetry entering `estop`; a pallet or forklift still inside a keep-clear zone for 20 s) open exactly the scene spec's incidents on the tune cases, none on the `C05` near-miss, and each window contains the annotated cause |
| Dataset version | `v1`, per-actor colour render; tune cases `case_01/03/04/05`; golden pair sealed |
| Preprocessing | Events as a processing run makes them (EXP-0006), merged by identity groups (EXP-0007), plus telemetry state changes read from the robot's scripted state channel only |
| Model / tracker version | `yolo11n-rewind-v1:native:conf0.25:iou0.5:edge16`, `bytetrack:buf30:match0.9:fps10`, `assoc:thr0.75:amb0.1:w0.35/0.4/0.25:gap15.0`, `incidents:estop10/10:dwell20+10/10:zonesZ2` |
| Hyperparameters | None swept. Thresholds and windows taken from the scene spec (§6.1, §6.4) |
| Hardware | Apple M4, MPS |
| Config version | `v0.1.0` |

## Metrics

`incidents-2026-09-13T114651Z`.

| Case | Expected | Mode | Opened | Latency | Window | Covers cause |
|---|---|---|---|---|---|---|
| case_01 | e-stop at 13.4 s, cause 12.8 s | perfect | e-stop | 0.0 s | 3.4–23.4 | yes |
| | | detections | e-stop | 0.0 s | 3.4–23.4 | yes |
| case_03 | e-stop at 17.4 s, cause 16.9 s | perfect | e-stop | 0.0 s | 7.4–27.4 | yes |
| | | detections | e-stop | 0.0 s | 7.4–27.4 | yes |
| case_04 | blocked at 34.0 s, cause 14.0 s | perfect | blocked | 0.4 s | 4.4–44.4 | yes |
| | | detections | blocked | 1.2 s | 5.2–44.9 | yes |
| case_05 | nothing | perfect | — | — | — | — |
| | | detections | — | — | — | — |

Totals per mode: 3 true positives, 0 false positives, 0 misses. The one negative case
opens nothing in either mode.

## Failure cases

No case was misclassified. What the numbers do not show:

| Case | What | Cause |
|---|---|---|
| case_01, case_03 | Latency exactly 0.0 s in both modes | By design, not by skill: the e-stop is read from telemetry, so class 1 detection does not touch perception at all. The difficulty of class 1 is the reconstruction (E7), and this experiment does not measure it |
| case_04 | Detected 1.2 s late on detections, 0.4 s on perfect tracks | A stop starts when speed first stays under 0.1 m/s for 1 s, so the stop is stamped after the drop, not at it. On exact positions that costs 0.4 s. The extra 0.8 s on detections is most likely back-projection jitter on a 0.15 m pallet box holding speed above the floor a little longer; not traced frame by frame. Harmless against a 20 s dwell |
| case_04 | Detections window ends at 44.9 s, not 45.2 s | Clipped to the last recorded frame, as intended |

## Result

The triggers do what the scene spec asks on every tune case, including the negative
one, and every rewind window contains its cause. The asymmetric class 2 window is what
makes the last column hold: a symmetric ten-second window would have opened at 24 s,
ten seconds after the drop.

Four cases, three positives and one negative, are not a precision estimate. The
false-alert rate here is 0 out of 1 negative case, which rules out a trigger that fires
on everything and says little else. The golden pair adds one class 1 case under
occlusion and one class 2 case with two candidate causes (E9.1).

## Decision

**Adopt** the triggers and windows as configured. Nothing here asks for a change.

## Next experiment

E7.2 hypothesis ranking inside these windows: cause top-1 against `cause_gt.json`.
